import os
import urllib, urllib2, cookielib
import contextlib
from PIL import Image
from StringIO import StringIO
import requests
from owslib.wms import WebMapService
from geonode.maps.models import Layer


def get_web_page(url, username=None, password=None, login_url=None):
    """Get url page possible with username and password.
    """

    if login_url:
        # Login via a form
        cookies = urllib2.HTTPCookieProcessor()
        opener = urllib2.build_opener(cookies)
        urllib2.install_opener(opener)

        opener.open(login_url)

        try:
            token = [x.value for x in cookies.cookiejar if x.name == 'csrftoken'][0]
        except IndexError:
            return False, "no csrftoken"

        params = dict(username=username, password=password, \
            this_is_the_login_form=True,
            csrfmiddlewaretoken=token,
            )
        encoded_params = urllib.urlencode(params)

        with contextlib.closing(opener.open(login_url, encoded_params)) as f:
            html = f.read()

    elif username is not None:
        # Login using basic auth

        # Create password manager
        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, username, password)

        # create the handler
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        opener = urllib2.build_opener(authhandler)
        urllib2.install_opener(opener)

    try:
        pagehandle = urllib2.urlopen(url)
    except urllib2.HTTPError, e:
        msg = ('The server couldn\'t fulfill the request. '
                'Error code: %s' % e.code)
        e.args = (msg,)
        raise
    except urllib2.URLError, e:
        msg = 'Could not open URL "%s": %s' % (url, e)
        e.args = (msg,)
        raise
    else:
        page = pagehandle.read()

    return page

def check_layer(uploaded):
    """Verify if an object is a valid Layer.
    """
    msg = ('Was expecting layer object, got %s' % (type(uploaded)))
    assert type(uploaded) is Layer, msg
    msg = ('The layer does not have a valid name: %s' % uploaded.name)
    assert len(uploaded.name) > 0, msg

def check_blank(content):
    """
    Uses PIL (Python Imaging Library to check if an image is a single colour - i.e. blank
    Images are loaded via a binary content string

    Checks for blank images based on the answer at:
    http://stackoverflow.com/questions/1110403/how-can-i-check-for-a-blank-image-in-qt-or-pyqt
    """

    im = Image.open(StringIO(content))
    # we need to force the image to load (PIL uses lazy-loading)
    # otherwise get the following error: AttributeError: 'NoneType' object has no attribute 'bands'
    im.load() 
    bands = im.split()

    # check if the image is completely white or black, if other background colours are used
    # these should be accounted for
    is_all_white = all(band.getextrema() == (255, 255)  for band in bands)
    is_all_black = all(band.getextrema() == (0, 0)  for band in bands)

    is_blank = (is_all_black or is_all_white)

    return is_blank

def get_default_parameters():

    params = {
        'TRANSPARENT': 'TRUE',
        'SERVICE': 'WMS',
        'VERSION': '1.1.1',
        'REQUEST': 'GetMap',
        'STYLES': '',
        'FORMAT': 'image/png',
        'WIDTH': '256',
        'HEIGHT': '256'}

    return params

def get_params_and_bounding_box(url, layer_name):

    params = get_default_parameters()
    
    # get bounding box for the layer
    wms = WebMapService(url, version='1.1.1')
    bounds = wms[layer_name].boundingBox

    if bounds is None:
        # some WMS servers only support a WGS84 boundingbox
        bounds = wms[layer_name].boundingBoxWGS84
        crs = 'EPSG:4326'
    else:
        # a bounding box and projection code are returned in the following
        # format: (0.0, 0.0, 500000.0, 500000.0, 'EPSG:29902')
        crs = bounds[4]
        
    bbox = ",".join([str(b) for b in bounds[:4]])

    # set the custom parameters for the layer
    params['LAYERS'] = layer_name
    params['BBOX'] = bbox
    params['SRS'] = crs

    return params

def check_blank_image(url, layer_name):
    """
    Check if the WMS layer at the WMS server specified in the
    URL returns a blank image when at the full extent
    """

    params = get_params_and_bounding_box(url, layer_name)
    resp = requests.get(url, params=params)
    print "The full URL request is '%s'" % resp.url

    # this should be 200
    print "The HTTP status code is: %i" % resp.status_code

    if resp.headers['content-type'] == 'image/png':
        # a PNG image was returned
        is_blank = check_blank(resp.content)
        if is_blank:
            print "A blank image was returned!"
        else:
            print "The image contains data."
    else:
        # if there are errors then these can be printed out here
        print resp.content
