# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
Combine 3 images to produce a properly-scaled RGB image following Lupton et al. (2004).

The three images must be aligned and have the same pixel scale and size.

For details, see : http://adsabs.harvard.edu/abs/2004PASP..116..133L
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import numpy as np
from . import ZScaleInterval


__all__ = ['make_lupton_rgb']


try:
    import scipy.misc
    scipy.misc.imresize  # checking if it exists
    HAVE_SCIPY_MISC = True
except (ImportError, AttributeError):
    HAVE_SCIPY_MISC = False

# NOTE: these methods would have come from LSST C++ code. They won't be available
# in astropy until they are converted somehow.
# from lsst.afw.display.displayLib import replaceSaturatedPixels, getZScale


def compute_intensity(image_r, image_g=None, image_b=None):
    """
    Return a naive total intensity from the red, blue, and green intensities.

    Parameters
    ----------
    image_r : `~numpy.ndarray`
        Intensity of image to be mapped to red; or total intensity if ``image_g``
        and ``image_b`` are None.
    image_g : `~numpy.ndarray`, optional
        Intensity of image to be mapped to green.
    image_b : `~numpy.ndarray`, optional
        Intensity of image to be mapped to blue.

    Returns
    -------
    intensity : `~numpy.ndarray`
        Total intensity from the red, blue and green intensities, or ``image_r``
        if green and blue images are not provided.
    """
    if image_g is None or image_b is None:
        if not (image_g is None and image_b is None):
            raise ValueError("please specify either a single image "
                             "or red, green, and blue images.")
        return image_r

    intensity = (image_r + image_g + image_b)/3.0

    # Repack into whatever type was passed to us
    return np.asarray(intensity, dtype=image_r.dtype)


class Mapping(object):
    """Baseclass to map red, blue, green intensities into uint8 values."""

    def __init__(self, minimum=None, image=None):
        """
        Create a mapping.

        Parameters
        ----------
        minimum : float or sequence(3)
            Intensity that should be mapped to black (a scalar or array for R, G, B).
        image : `~numpy.ndarray`, optional
            The image to be used to calculate the mapping.
            If provided, it is also used as the default for make_rgb_image().
        """
        self._uint8Max = float(np.iinfo(np.uint8).max)

        try:
            len(minimum)
        except TypeError:
            minimum = 3*[minimum]
        if len(minimum) != 3:
            raise ValueError("please provide 1 or 3 values for minimum.")

        self.minimum = minimum
        self._image = np.asarray(image)

    def make_rgb_image(self, image_r=None, image_g=None, image_b=None,
                       x_size=None, y_size=None, rescale=None):
        """
        Convert 3 arrays, image_r, image_g, and image_b into an 8-bit RGB image.

        Parameters
        ----------
        image_r : `~numpy.ndarray`, optional
            Image to map to red (if None, use the image passed to the
            constructor).
        image_g : `~numpy.ndarray`, optional
            Image to map to green (if None, use image_r).
        image_b : `~numpy.ndarray`, optional
            Image to map to blue (if None, use image_r).
        x_size : int, optional
            Desired width of RGB image (or None).  If y_size is None, preserve
            aspect ratio.
        y_size : int, optional
            Desired height of RGB image (or None).
        rescale : float, optional
            Make size of output image rescale*size of the input image.
            Cannot be specified if x_size or y_size are given.

        Returns
        -------
        RGBimage : `~numpy.ndarray`
            RGB (integer, 8-bits per channel) color image as an NxNx3 numpy array.
        """
        if image_r is None:
            if self._image is None:
                raise RuntimeError("you must provide an image or pass one "
                                   "to the constructor.")
            image_r = self._image
        else:
            image_r = np.asarray(image_r)

        if image_g is None:
            image_g = image_r
        else:
            image_g = np.asarray(image_g)

        if image_b is None:
            image_b = image_r
        else:
            image_b = np.asarray(image_b)

        if x_size is not None or y_size is not None:
            if rescale is not None:
                raise ValueError("you may not specify a size and rescale.")
            h, w = image_r.shape
            if y_size is None:
                y_size = int(x_size*h/float(w) + 0.5)
            elif x_size is None:
                x_size = int(y_size*w/float(h) + 0.5)

            # need to cast to int when passing tuple to imresize.
            size = (int(y_size), int(x_size))  # n.b. y, x order for scipy
        elif rescale is not None:
            size = float(rescale)  # a float is intepreted as a percentage
        else:
            size = None

        if size is not None:
            if not HAVE_SCIPY_MISC:
                raise RuntimeError("unable to rescale as scipy.misc.imresize "
                                   "is unavailable.")

            image_r = scipy.misc.imresize(image_r, size, interp='bilinear',
                                          mode='F')
            image_g = scipy.misc.imresize(image_g, size, interp='bilinear',
                                          mode='F')
            image_b = scipy.misc.imresize(image_b, size, interp='bilinear',
                                          mode='F')

        return np.dstack(self._convert_images_to_uint8(image_r, image_g, image_b)).astype(np.uint8)

    def intensity(self, image_r, image_g, image_b):
        """
        Return the total intensity from the red, blue, and green intensities.
        This is a naive computation, and may be overridden by subclasses.

        Parameters
        ----------
        image_r : `~numpy.ndarray`
            Intensity of image to be mapped to red; or total intensity if
            ``image_g`` and ``image_b`` are None.
        image_g : `~numpy.ndarray`, optional
            Intensity of image to be mapped to green.
        image_b : `~numpy.ndarray`, optional
            Intensity of image to be mapped to blue.

        Returns
        -------
        intensity : `~numpy.ndarray`
            Total intensity from the red, blue and green intensities, or
            ``image_r`` if green and blue images are not provided.
        """
        return compute_intensity(image_r, image_g, image_b)

    def map_intensity_to_uint8(self, I):
        """
        Return an array which, when multiplied by an image, returns that image
        mapped to the range of a uint8, [0, 255] (but not converted to uint8).

        The intensity is assumed to have had minimum subtracted (as that can be
        done per-band).

        Parameters
        ----------
        I : `~numpy.ndarray`
            Intensity to be mapped.

        Returns
        -------
        mapped_I : `~numpy.ndarray`
            ``I`` mapped to uint8
        """
        with np.errstate(invalid='ignore', divide='ignore'):
            return np.clip(I, 0, self._uint8Max)

    def _convert_images_to_uint8(self, image_r, image_g, image_b):
        """Use the mapping to convert images image_r, image_g, and image_b to a triplet of uint8 images"""
        image_r = image_r - self.minimum[0]  # n.b. makes copy
        image_g = image_g - self.minimum[1]
        image_b = image_b - self.minimum[2]

        fac = self.map_intensity_to_uint8(self.intensity(image_r, image_g, image_b))

        image_rgb = [image_r, image_g, image_b]
        for c in image_rgb:
            c *= fac
            c[c < 0] = 0                # individual bands can still be < 0, even if fac isn't

        pixmax = self._uint8Max
        r0, g0, b0 = image_rgb           # copies -- could work row by row to minimise memory usage

        with np.errstate(invalid='ignore', divide='ignore'):  # n.b. np.where can't and doesn't short-circuit
            for i, c in enumerate(image_rgb):
                c = np.where(r0 > g0,
                             np.where(r0 > b0,
                                      np.where(r0 >= pixmax, c*pixmax/r0, c),
                                      np.where(b0 >= pixmax, c*pixmax/b0, c)),
                             np.where(g0 > b0,
                                      np.where(g0 >= pixmax, c*pixmax/g0, c),
                                      np.where(b0 >= pixmax, c*pixmax/b0, c))).astype(np.uint8)
                c[c > pixmax] = pixmax

                image_rgb[i] = c

        return image_rgb


class LinearMapping(Mapping):
    """A linear map map of red, blue, green intensities into uint8 values"""

    def __init__(self, minimum=None, maximum=None, image=None):
        """
        A linear stretch from [minimum, maximum].
        If one or both are omitted use image min and/or max to set them.

        Parameters
        ----------
        minimum : float
            Intensity that should be mapped to black (a scalar or array for R, G, B).
        maximum : float
            Intensity that should be mapped to white (a scalar).
        """

        if minimum is None or maximum is None:
            if image is None:
                raise ValueError("you must provide an image if you don't "
                                 "set both minimum and maximum")
            if minimum is None:
                minimum = image.min()
            if maximum is None:
                maximum = image.max()

        Mapping.__init__(self, minimum=minimum, image=image)
        self.maximum = maximum

        if maximum is None:
            self._range = None
        else:
            if maximum == minimum:
                raise ValueError("minimum and maximum values must not be equal")
            self._range = float(maximum - minimum)

    def map_intensity_to_uint8(self, I):
        with np.errstate(invalid='ignore', divide='ignore'):  # n.b. np.where can't and doesn't short-circuit
            return np.where(I <= 0, 0,
                            np.where(I >= self._range, self._uint8Max/I, self._uint8Max/self._range))


class AsinhMapping(Mapping):
    """
    A mapping for an asinh stretch (preserving colours independent of brightness)

    x = asinh(Q (I - minimum)/range)/Q

    This reduces to a linear stretch if Q == 0

    See http://adsabs.harvard.edu/abs/2004PASP..116..133L
    """

    def __init__(self, minimum, stretch, Q=8):
        """
        asinh stretch from minimum to minimum + stretch, scaled by Q, via:
            x = asinh(Q (I - minimum)/stretch)/Q

        Parameters
        ----------

        minimum : float
            Intensity that should be mapped to black (a scalar or array for R, G, B).
        stretch : float
            The linear stretch of the image.
        Q : float
            The asinh softening parameter.
        """
        Mapping.__init__(self, minimum)

        epsilon = 1.0/2**23            # 32bit floating point machine epsilon; sys.float_info.epsilon is 64bit
        if abs(Q) < epsilon:
            Q = 0.1
        else:
            Qmax = 1e10
            if Q > Qmax:
                Q = Qmax

        frac = 0.1                  # gradient estimated using frac*stretch is _slope
        self._slope = frac*self._uint8Max/np.arcsinh(frac*Q)

        self._soften = Q/float(stretch)

    def map_intensity_to_uint8(self, I):
        with np.errstate(invalid='ignore', divide='ignore'):  # n.b. np.where can't and doesn't short-circuit
            return np.where(I <= 0, 0, np.arcsinh(I*self._soften)*self._slope/I)


class AsinhZScaleMapping(AsinhMapping):
    """
    A mapping for an asinh stretch, estimating the linear stretch by zscale.

    x = asinh(Q (I - z1)/(z2 - z1))/Q

    See AsinhMapping

    """

    def __init__(self, image1, image2=None, image3=None, Q=8, pedestal=None):
        """
        Create an asinh mapping from an image, setting the linear part of the
        stretch using zscale.

        Parameters
        ----------
        image1 : `~numpy.ndarray` or a list of arrays
            The image to analyse, or a list of 3 images to be converted to
            an intensity image.
        image2 : `~numpy.ndarray`, optional
            the second image to analyse (must be specified with image3).
        image3 : `~numpy.ndarray`, optional
            the third image to analyse (must be specified with image2).
        Q : float, optional
            The asinh softening parameter. Default is 8.
        pedestal : float or sequence(3), optional
            The value, or array of 3 values, to subtract from the images; or None.

        Notes
        -----
        N.b. pedestal, if not None, is removed from the images when
        calculating the zscale stretch, and added back into
        Mapping.minimum[]
        """

        if image2 is None or image3 is None:
            if not (image2 is None and image3 is None):
                raise ValueError("please specify either a single image "
                                 "or three images.")
            image = [image1]
        else:
            image = [image1, image2, image3]

        if pedestal is not None:
            try:
                len(pedestal)
            except TypeError:
                pedestal = 3*[pedestal]

            if len(pedestal) != 3:
                raise ValueError("please provide 1 or 3 pedestals.")

            image = list(image)        # needs to be mutable
            for i, im in enumerate(image):
                if pedestal[i] != 0.0:
                    image[i] = im - pedestal[i]  # n.b. a copy
        else:
            pedestal = len(image)*[0.0]

        image = compute_intensity(*image)

        zscale_limits = ZScaleInterval().get_limits(image)
        zscale = LinearMapping(*zscale_limits, image=image)
        stretch = zscale.maximum - zscale.minimum[0]  # zscale.minimum is always a triple
        minimum = zscale.minimum

        for i, level in enumerate(pedestal):
            minimum[i] += level

        AsinhMapping.__init__(self, minimum, stretch, Q)
        self._image = image


def make_lupton_rgb(image_r, image_g=None, image_b=None, minimum=0, stretch=5, Q=8,
                    saturated_border_width=0, saturated_pixel_value=None,
                    x_size=None, y_size=None, rescale=None,
                    filename=None):
    """
    Return a Red/Green/Blue color image from up to 3 images using an asinh stretch.
    The input images can be int or float, and in any range or bit-depth.

    For a more detailed look at the use of this method, see the document
    :ref:`astropy-visualization-rgb`.

    Parameters
    ----------

    image_r : `~numpy.ndarray`
        Image to map to red.
    image_g : `~numpy.ndarray`
        Image to map to green (if None, use image_r).
    image_b : `~numpy.ndarray`
        Image to map to blue (if None, use image_r).
    minimum : float
        Intensity that should be mapped to black (a scalar or array for R, G, B).
    stretch : float
        The linear stretch of the image.
    Q : float
        The asinh softening parameter.
    saturated_border_width : int
        If saturated_border_width is non-zero, replace saturated pixels with saturated_pixel_value.
    saturated_pixel_value : float
        Value to replace saturated pixels with.
    x_size : int
        Desired width of RGB image (or None).  If y_size is None, preserve aspect ratio.
    y_size : int
        Desired height of RGB image (or None).
    rescale : float
        Make size of output image rescale*size of the input image.
        Cannot be specified if x_size or y_size are given.
    filename: str
        Write the resulting RGB image to a file (file type determined frome extension).

    Returns
    -------
    rgb : `~numpy.ndarray`
        RGB (integer, 8-bits per channel) color image as an NxNx3 numpy array.
    """
    image_r = image_r
    if image_g is None:
        image_g = image_r
    if image_b is None:
        image_b = image_r

    if saturated_border_width:
        if saturated_pixel_value is None:
            raise ValueError("saturated_pixel_value must be set if "
                             "saturated_border_width is set.")
        msg = "Cannot do this until we extract replaceSaturatedPixels out of afw/display/saturated.cc"
        raise NotImplementedError(msg)
        # replaceSaturatedPixels(image_r, image_g, image_b, saturated_border_width, saturated_pixel_value)

    asinhMap = AsinhMapping(minimum, stretch, Q)
    rgb = asinhMap.make_rgb_image(image_r, image_g, image_b,
                                  x_size=x_size, y_size=y_size, rescale=rescale)

    if filename:
        import matplotlib.image
        matplotlib.image.imsave(filename, rgb)

    return rgb
