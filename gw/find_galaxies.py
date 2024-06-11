#!/usr/bin/env python

import healpy as hp 
import numpy as np
from astropy.io import fits
from astropy.table import Table
from configparser import ConfigParser
from scipy.stats import norm
#from scipy.special import gammaincinv
#from scipy.special import gammaincc
from ligo.skymap import distance

from gw.models import GWFollowupGalaxy
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)
BASE_DIR = settings.BASE_DIR


def generate_galaxy_list(eventlocalization, completeness=None, credzone=None, skymap_filepath=None):
    """
    An adaptation of the galaxy ranking algorithm described in
    Arcavi et al. 2017 (doi:10.3847/2041-8213/aa910f)
    
    eventlocalization: an EventLocalization object
    """

    # Parameters:
    config = ConfigParser(inline_comment_prefixes=';')
    config.read(os.path.join(BASE_DIR, 'gw/gw_config.ini'))
    
    catalog_path = config.get('GALAXIES', 'CATALOG_PATH') # Path to numpy file containing the galaxy catalog (faster than getting from the db)
    
    # Matching parameters:
    if not credzone:
        credzone = float(config.get('GALAXIES', 'CREDZONE')) # Localization probability to consider credible (e.g. 0.99)
    nsigmas_in_d = float(config.get('GALAXIES', 'NSIGMAS_IN_D')) # Sigmas to consider in distnace (e.g. 3)
    if not completeness:
        completeness = float(config.get('GALAXIES', 'COMPLETENESSP')) # Mass fraction completeness (e.g. 0.5)
    minGalaxies = int(config.get('GALAXIES', 'MINGALAXIES')) # Minimum number of galaxies to output (e.g. 100)
    
    minL = float(config.get('GALAXIES', 'MINL')) # Estimated brightest KN luminosity
    maxL = float(config.get('GALAXIES', 'MAXL')) # Estimated faintest KN luminosity
    sensitivity = float(config.get('GALAXIES', 'SENSITIVITY')) # Estimatest faintest app mag we can see
    ngalaxtoshow = int(config.get('GALAXIES', 'NGALAXIES')) # Number of galaxies to show
    
    mindistFactor = float(config.get('GALAXIES', 'MINDISTFACTOR')) #reflecting a small chance that the theory is comletely wrong and we can still see something
    
    ## Schecter Function parameters:
    #alpha = float(config.get('GALAXIES', 'ALPHA'))
    #MB_star = float(config.get('GALAXIES', 'MB_STAR'))
    
    try:
        if skymap_filepath is not None:
            prob, distmu, distsigma, distnorm = hp.read_map(skymap_filepath, field=[0,1,2,3], verbose=False)
        else:
            prob, distmu, distsigma, distnorm = hp.read_map(eventlocalization.skymap_url.replace('.multiorder.fits','.fits.gz'), field=[0,1,2,3], verbose=False)

    except Exception as e:
        logger.warning('Failed to read sky map for {}'.format(eventlocalization))
        logger.warning(e)
        return

    # Get the map parameters:
    npix = len(prob)
    nside = hp.npix2nside(npix)

    # Load the galaxy catalog.
    logger.info('Loading Galaxy Catalog')
    galaxies = Table.read(catalog_path)
    
    ### If using luminosity, remove galaxies with no Lum_X, like so:q
    #galaxies = galaxies[~np.isnan(galaxies['Lum_W1'])]
    ### If using mass, make cuts on DistMpc and Mstar
    galaxies = galaxies[~np.isnan(galaxies['Mstar'])]
    galaxies = galaxies[np.where(galaxies['DistMpc']>0)] # Remove galaxies with distance < 0

    theta = 0.5 * np.pi - np.pi*(galaxies['dec'])/180
    phi = np.deg2rad(galaxies['ra'])
    d = np.array(galaxies['DistMpc'])
    # Convert galaxy coordinates to map pixels:
    logger.info('Converting Galaxy Coordinates to Map Pixels')
    ipix = hp.ang2pix(nside, theta, phi)

    maxprobcoord_tup = hp.pix2ang(nside, np.argmax(prob))
    maxprobcoord = [0, 0]
    maxprobcoord[0] = np.rad2deg(0.5*np.pi-maxprobcoord_tup[0])
    maxprobcoord[1] = np.rad2deg(maxprobcoord_tup[1])
    
    #Find the zone with probability <= credzone:
    logger.info('Finding zone with credible probability')
    probcutoff = 1
    probsum = 0

    sortedprob = np.sort(prob,kind="mergesort")
    while probsum < credzone:
        probsum = probsum + sortedprob[-1]
        probcutoff = sortedprob[-1]
        sortedprob = sortedprob[:-1]

    # Calculate the probability for galaxies according to the localization map:
    logger.info('Calculating galaxy probabilities')
    p = prob[ipix]
    distp = (norm(distmu[ipix], distsigma[ipix]).pdf(d) * distnorm[ipix])

    # Cuttoffs: credzone of probability by angles and nsigmas by distance:
    inddistance = np.where(np.abs(d-distmu[ipix])<nsigmas_in_d*distsigma[ipix])
    indcredzone = np.where(p>=probcutoff)

    doMassCuttoff = True

    # Increase credzone to 99.995% if no galaxies found:
    # If no galaxies found in the credzone and within the right distance range
    if len(galaxies[np.intersect1d(indcredzone,inddistance)]) == 0:
        while probsum < 0.99995:
            if sortedprob.size == 0:
                break
            probsum = probsum + sortedprob[-1]
            probcutoff = sortedprob[-1]
            sortedprob = sortedprob[:-1]
        inddistance = np.where(np.abs(d - distmu[ipix]) < 5 * distsigma[ipix])
        indcredzone = np.where(p >= probcutoff)
        doMassCuttoff = False

    ipix = ipix[np.intersect1d(indcredzone, inddistance)]
    p = p[np.intersect1d(indcredzone, inddistance)]
    p = (p * (distp[np.intersect1d(indcredzone, inddistance)]))  ##d**2?

    galaxies = galaxies[np.intersect1d(indcredzone, inddistance)]
    if len(galaxies) == 0:
        logger.warning("No galaxies found")
        logger.warning("Peak is at [RA,DEC](deg) = {}".format(maxprobcoord))
        return

    ### Normalize by mass:
    ### NOTE: Can also do this in using luminosity (commented out)

    mass = galaxies['Mstar']
    massNorm = mass / np.sum(mass)
    massnormalization = np.sum(mass)
    normalization = np.sum(p * massNorm)

    #luminosity = mag.L_nu_from_magAB(galaxies['Bmag'] - 5 * np.log10(galaxies['Dist'] * (10 ** 5)))
    #luminosityNorm = luminosity / np.sum(luminosity)
    #luminositynormalization = np.sum(luminosity)
    #normalization = np.sum(p * luminosityNorm)

    #taking 50% of mass (missingpiece is the area under the schecter function between l=inf and the brightest galaxy in the field.
    #if the brightest galaxy in the field is fainter than the schecter function cutoff- no cutoff is made.
    #while the number of galaxies in the field is smaller than minGalaxies- we allow for fainter galaxies, until we take all of them.

    ### NOTE: Can skip this block if using mass
    #missingpiece = gammaincc(alpha + 2, 10 ** (-(min(galaxies['Bmag']-5*np.log10(galaxies['Dist']*(10**5))) - MB_star) / 2.5)) ##no galaxies brighter than this in the field- so don't count that part of the Schechter function

    #while doMassCuttoff:
    #    MB_max = MB_star + 2.5 * np.log10(gammaincinv(alpha + 2, completeness+missingpiece))

    #    if (min(galaxies['Bmag']-5*np.log10(galaxies['Dist']*(10**5))) - MB_star)>0: #if the brightest galaxy in the field is fainter then cutoff brightness- don't cut by brightness
    #        MB_max = 100

    #    brightest = np.where(galaxies['Bmag']-5*np.log10(galaxies['Dist']*(10**5))<MB_max)
    #    if len(brightest[0])<minGalaxies:
    #        if completeness>=0.9: #tried hard enough. just take all of them
    #            completeness = 1 # just to be consistent.
    #            doMassCuttoff = False
    #        else:
    #            completeness = (completeness + (1. - completeness) / 2)
    #    else: #got enough galaxies
    #        galaxies = galaxies[brightest]
    #        p = p[brightest]
    #        luminosityNorm = luminosityNorm[brightest]
    #        doMassCuttoff = False

    # Accounting for distance
    absolute_sensitivity = sensitivity - 5 * np.log10(galaxies['DistMpc'] * (10 ** 5))

    #absolute_sensitivity_lum = mag.f_nu_from_magAB(absolute_sensitivity)
    absolute_sensitivity_lum = 4e33 * 10**(0.4*(4.74-absolute_sensitivity)) # Check this?
    distanceFactor = np.zeros(len(galaxies))

    distanceFactor[:] = ((maxL - absolute_sensitivity_lum) / (maxL - minL))
    distanceFactor[mindistFactor>(maxL - absolute_sensitivity_lum) / (maxL - minL)] = mindistFactor
    distanceFactor[absolute_sensitivity_lum<minL] = 1
    distanceFactor[absolute_sensitivity>maxL] = mindistFactor

    # Sorting glaxies by probability
    ii = np.argsort(p*massNorm*distanceFactor,kind="mergesort")[::-1]

    ####counting galaxies that constitute 50% of the probability(~0.5*0.98)
    summ = 0
    galaxies50per = 0
    sum_seen = 0
    enough = True
    while summ<0.5:
        if galaxies50per>= len(ii):
            enough = False
            break
        summ = summ + (p[ii[galaxies50per]]*massNorm[ii[galaxies50per]])/float(normalization)
        sum_seen = sum_seen + (p[ii[galaxies50per]]*massNorm[ii[galaxies50per]]*distanceFactor[ii[galaxies50per]])/float(normalization)
        galaxies50per = galaxies50per+1

    if len(ii) > ngalaxtoshow:
        n = ngalaxtoshow
    else:
        n = len(ii)

    ### Save the galaxies in the database
    for i in range(ii.shape[0])[:n]:
        ind = ii[i]
        newgalaxyrow = GWFollowupGalaxy(catalog='NEDLVSCatalog', 
                                        catalog_objname=galaxies[ind]['objname'],
                                        ra=galaxies[ind]['ra'], 
                                        dec=galaxies[ind]['dec'],
                                        dist=galaxies[ind]['DistMpc'], 
                                        score=(p * massNorm / normalization)[ind],
                                        eventlocalization=eventlocalization
                        )
        newgalaxyrow.save()
   
    logger.info('Finished creating ranked galaxy list for EventLocalization {}'.format(eventlocalization))
