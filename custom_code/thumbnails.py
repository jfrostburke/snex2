#!/usr/bin/env python

"""
Convert FITS data in to a standard web displayable format (e.g. GIF).
Modified from SNEx
"""
import sys
import os
import numpy as np
from astropy.io import fits
from PIL import Image, ImageDraw
from struct import pack, unpack


# ************************************************************
class ImageThumb:
    """
    Load in FITS data and output thumbs
    """
    # default parameters
    grow = 1.0 / 12.0  # scaling parameter for the resizing
    imtype = 'webp'  # type of image to output/create
    basename = ''  # root name for the output images
    outdir = '/home/cpellegrino/Downloads/'  # directory for the output images
    sky = None  # fix sky background level for all images?
    sig = None  # fix image (color) range for all images?
    verbose = True  # print out steps *** turn this off if serving images! ***
    region = None  # [x1, x2, y1, y2] list for the sub array or None for whole image
    skip = 0  # skip this number of rows and columns in the data array between used pixels
    datacube = []  # holds a list of tuples with the chip_id and data for each extension
    fixscale = None  # adjust scaling relative to this chip so that the backgrounds come out level

    def __init__(self, imagepath, region=None, skip=0, grow=None, verbose=True, fixscale=None,
                 fitsext=None):
        # location of the data and the image name
        self.datadir, self.imname = os.path.split(imagepath)

        # get the base name for the thumbs
        self.basename, ext = os.path.splitext(self.imname)

        # initialize the list to hold each extension's data
        self.datacube = []

        # resizing scale factor
        if grow:
            self.grow = grow

        # print out processing steps?
        self.verbose = verbose

        # just work on a sub array?
        self.region = region

        # skip lines and columns?
        self.skip = skip

        # normalize the sky background?
        self.fixscale = fixscale

        # open the image
        hlist = fits.open(imagepath)

        hdu = hlist[0]
        if self.region:
            data = getdata(imagepath, region=self.region, skip=self.skip, ext=0)

        else:
            data = hdu.data
            
        chip_id = int(hdu.header.get('CCDID', default=len(self.datacube)))
        self.datacube.append((chip_id, data))

        hlist.close()

    # ***********
    def prepare_image(self, data):
        """
        Resize and scale the data.

        """
        # convert the data to the requested image format
        im = Image.fromarray(data.astype(np.uint8), mode='L')

        if self.grow < 1.0:
            # shrink image
            filt = Image.ANTIALIAS
        else:
            # grow image
            filt = Image.NEAREST

        # resize the image
        nx, ny = im.size
        im = im.resize((int(nx * self.grow), int(ny * self.grow)), filt)

        # now flip/rotate the image as appropiate
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
        return im

    # ***********
    def write_thumb(self):
        """
        Write out each image in the datacube as a thumbnail.
        """

        # loop over each data array
        for chip, data in self.datacube:
            if len(self.datacube) == 1:
                self.write_image(data, self.basename)
            else:
                self.write_image(data, "%s_%2.2d" % (self.basename, chip))

    # ***********
    def write_image(self, data, imbase):
        """
        Save this image to disk.

        """

        # get the image data ready
        data = make_depth_256(data, sky=self.sky, sig=self.sig)
        im = self.prepare_image(data)

        # output the thumbnail image
        imname = "%s%s.%s" % (self.outdir, imbase, self.imtype)
        if self.verbose:
            print('creating ', imname, ' ...')
        im.save(imname)



# ************************************************************
def getsky(data):
    """
    Determine the sky parameters for a FITS data extension.

    data -- array holding the image data
    """

    # maximum number of interations for mean,std loop
    maxiter = 30

    # maximum number of data points to sample
    maxsample = 10000

    # size of the array
    ny, nx = data.shape

    # how many sampels should we take?
    if data.size > maxsample:
        nsample = maxsample
    else:
        nsample = data.size

    # create sample indicies
    xs = np.random.uniform(low=0, high=nx, size=nsample).astype('L')
    ys = np.random.uniform(low=0, high=ny, size=nsample).astype('L')

    # sample the data
    sample = data[ys, xs].copy()
    sample = sample.reshape(nsample)

    # determine the clipped mean and standard deviation
    mean = sample.mean()
    std = sample.std()
    oldsize = 0
    niter = 0
    while oldsize != sample.size and niter < maxiter:
        niter += 1
        oldsize = sample.size
        wok = (sample < mean + 3 * std)
        sample = sample[wok]
        wok = (sample > mean - 3 * std)
        sample = sample[wok]
        mean = sample.mean()
        std = sample.std()

    return mean, std


# ************************************************************
def make_depth_256(data, sky=None, sig=None, depth=256, zerosig=-1, spansig=6):
    """
    Convert image to 256 colors.

    data is an image array

    Scale image data so that black is (sky - sig) and white is (sky + 5
    * sig). If optional sky and sig keywords are not set, they are
    calculated using getsky(data)

   """
    data = data.astype(np.float64)
    if sky is None or sig is None:
        # get the scaling parameters
        sky2, sig2 = getsky(data)
        if sky is None:
            sky = sky2
        if sig is None:
            sig = sig2

    # set the color range
    zero = sky + zerosig * sig
    span = spansig * sig

    # scale the data to the requested display values
    # greys
    data -= zero
    data *= (depth - 1) / span

    # black
    w = data < 0
    data[w] = 0

    # white
    w = data > (depth - 1)
    data[w] = (depth - 1)

    data += 256 - depth

    return data


# ************************************************************
DATATYPES = {}
class intdata:
    type = 'i'
    nbytes = 2
    format = 'h'
DATATYPES[16] = intdata
class floatdata:
    type = 'f'
    nbytes = 4
    format = 'f'
DATATYPES[32] = floatdata
class floatdata64:
    type = 'f'
    nbytes = 4
    format = 'f'
DATATYPES[64] = floatdata64

BLOCKSIZE = 2880 # FITS standard


# ************************************************************
def gethead(filename, fp=None, ext=0):
    """
    Read a FITS header and return import keywords and data section index.
    """

    # get the file pointer
    if fp:
        f = fp
    else:
        f=open(filename, 'rb')

    nx = 0
    ny = 0
    datasize = 0
    for ex in range(ext + 1):
        # jump to the next header
        f.seek(nx * ny * datasize, 1)
        pos = f.tell()
        if pos % BLOCKSIZE != 0:
            shift = BLOCKSIZE - (pos % BLOCKSIZE)
            f.seek(shift, 1)

        # read in the header
        header = {}
        line=f.read(80).decode('UTF-8') # first line
        while line[:3] != "END":
            key = line[:8].strip()
            val = line[9:].split('/')[0].strip()
            header[key] = val

            # read the next line
            line=f.read(80).decode('UTF-8')


        if 'NAXIS1' in header.keys():
            nx = int(header['NAXIS1'])
        else:
            nx = 0
        if 'NAXIS2' in header.keys():
            ny = int(header['NAXIS2'])
        else:
            ny = 0
        if 'BITPIX' in header.keys():
            datasize = abs(int(header['BITPIX']))/8
        else:
            datasize = 0

        # jump to the start of the data section
        pos = f.tell()
        if pos % BLOCKSIZE != 0:
            shift = BLOCKSIZE - (pos % BLOCKSIZE)
            f.seek(shift, 1)
        startpos = f.tell()

    # close file if opened locally
    if not fp: f.close()

    return (startpos, header)


# ***************************************************************************
def getdata(filename, region=None, skip=0, ext=0):
    """
    Read out a sub section of data from a FITS file

    filename  full path to the FITS file.
    region    subsection to extract [x1, x2, y1, y2]
    skip      integer of rows, columns to skip between reads
    """

    # get the file pointer
    f=open(filename, 'rb')#,errors='ignore')

    # read in the header
    startpos, header = gethead(filename, fp=f, ext=ext)

    # grab the keywords necessary to parse the data
    nx = int(header['NAXIS1'])
    ny = int(header['NAXIS2'])
    bitpix = abs(int(header['BITPIX']))
    if 'BZERO' in header.keys():
        bzero = float(header['BZERO'])
    else:
        bzero = None
    if 'BSCALE' in header.keys():
        bscale = float(header['BSCALE'])
    else:
        bscale = None

    # set the data type to read
    datatype = DATATYPES[bitpix]

    # set the region to the full frame if not specified
    if region == None:
        region = [0, nx-1, 0, ny-1]

    # initalize the subarray
    x1, x2, y1, y2 = region
    if x1 < 0: x1 = 0
    if y1 < 0: y1 = 0
    if x2 >= nx: x2 = nx-1
    if y2 >= ny: y2 = ny-1
    nx2 = int(round((x2 - x1) / (skip + 1) + 1))
    ny2 = int(round((y2 - y1) / (skip + 1) + 1))
    section = np.zeros((ny2, nx2), dtype=datatype.type)   #### fix! ####

    # read in a continuous line and then throw away any skipped columns
    fmt = "%s%dx" % (datatype.format, skip * datatype.nbytes)
    fmt = '>' + (fmt * nx2)
    buffsize = nx2 * (1 + skip) * datatype.nbytes
    jumpsize = nx * (1 + skip) * datatype.nbytes
    
    # read in the sub array
    f.seek(startpos)

    # jump to the first section column
    f.seek((nx * y1 + x1) * datatype.nbytes, 1)
    for j in range(ny2):
        pos = f.tell()

        # read in the data
        section[j, :] = unpack(fmt, f.read(buffsize))

        # jump to the next row
        f.seek(pos + jumpsize, 0)

    # we're done reading the file
    f.close()

    # scale the data as necessary
    if bscale: section *= bscale
    if bzero: section += bzero

    return section


# ***************************************************************************
def make_thumb(files, grow=1.0, sky=None, sig=None, x=900, y=900, width=250, height=250, ticks=False, spansig=4, skip=0, fixscale=None):
    """
    Make thumbnails from a FITS image
    """
    region = [x-width, x+width, y-height, y+height]
    # make the thumbnails
    outfiles = []
    for filename in files:
        # See if fits file needs to be funpacked
        if not os.path.exists(filename):
            r = os.system('funpack -D '+filename+'.fz')

        # load in the image data
        thumb = ImageThumb(filename, region=region, skip=skip, grow=grow, verbose=True)
        data = thumb.datacube[0][1].copy()
        data = make_depth_256(data, sky=thumb.sky, sig=thumb.sig, zerosig=0, spansig=spansig)

        im = thumb.prepare_image(data).convert('RGB')

        ### Do rotations and reflections here

        ### Add crosshair
        if ticks:
            x1, x2, y1, y2 = region
            xoff = -0.5
            yoff = 1.0

            x_new = int(round((x + xoff - max([0, x1])) * grow))
            y_new = int(round((min([y2, 4096]) - y + yoff) * grow))
            
            draw = ImageDraw.Draw(im)
            draw.line((x_new,y_new+7,x_new,y_new+25), fill='white')
            draw.line((x_new-7,y_new,x_new-25,y_new), fill='white')

        # make the thumbs
        outfile = 'data/thumbs/'+filename.split('/')[-1].replace('.fits', '.webp')
        f = open(outfile, 'wb')
        im.save(f, 'WEBP')
        f.close()

        outfiles.append(filename.split('/')[-1].replace('.fits', '.webp'))#outfile)

    return outfiles
