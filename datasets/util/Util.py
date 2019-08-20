import os
import random

import numpy as np
import skimage.measure as skimage_measure
import tensorflow as tf
from scipy.ndimage import distance_transform_edt
from skimage import color
from skimage.draw import circle
from scipy.stats import norm

from datasets import DataKeys


def username():
  return os.environ["USER"]


def get_filename_without_extension(path):
  file_name = path.split("/")[-1]
  file_name_wihout_ext = file_name.split(".")[0]
  return file_name_wihout_ext


def resize_image(img, out_size, bilinear):
  if bilinear:
    img = tf.image.resize_images(img, out_size)
  else:
    img = tf.image.resize_nearest_neighbor(tf.expand_dims(img, 0), out_size)
    img = tf.squeeze(img, 0)
  return img


def resize_coords(tensor, out_size, original_size):
  y_ratio = tf.ones([tf.shape(tensor)[0], 1]) * tf.cast(out_size[0] / original_size[0], tf.float32)
  x_ratio = tf.ones([tf.shape(tensor)[0], 1]) * tf.cast(out_size[1] / original_size[1], tf.float32)
  tensor = tf.cast(tensor, tf.float32)

  tensor *= tf.concat([y_ratio, x_ratio, y_ratio, x_ratio], axis=1)
  return tensor


def flip_coords_horizontal(tensor, original_width):
  #original_width_f = tf.cast(original_width, tf.float32)
  original_width_f = tf.cast(original_width, tensor.dtype)
  return tf.stack([tensor[..., 0], original_width_f - tensor[..., 3], tensor[..., 2],
                   original_width_f - tensor[..., 1]], axis=-1)


def random_crop_image(img, size, offset=None):
  # adapted from code from tf.random_crop
  shape = tf.shape(img)
  #remove the assertion for now since it makes the queue filling slow for some reason
  #check = tf.Assert(
  #  tf.reduce_all(shape[:2] >= size),
  #  ["Need value.shape >= size, got ", shape, size])
  #with tf.control_dependencies([check]):
  #  img = tf.identity(img)
  limit = shape[:2] - size + 1
  dtype = tf.int32
  if offset is None:
    offset = tf.random_uniform(shape=(2,), dtype=dtype, maxval=dtype.max, seed=None) % limit
    offset = tf.stack([offset[0], offset[1], 0])
  size0 = size[0] if isinstance(size[0], int) else None
  size1 = size[1] if isinstance(size[1], int) else None
  size_im = tf.stack([size[0], size[1], img.get_shape().as_list()[2]])
  img_cropped = tf.slice(img, offset, size_im)
  out_shape_img = [size0, size1, img.get_shape()[2]]
  img_cropped.set_shape(out_shape_img)
  return img_cropped, offset


def visualise_clicks(images, click_maps, c, gaussian=False):
  out_imgs = None
  if not isinstance(c, str):
    c=c.decode('utf-8')
  for idx in range(len(images)):
    img = images[idx]
    click_map = click_maps[idx]
    # Radius of the point to be diplayed
    r=3
    if gaussian and np.unique(click_map) > 1:
      pts = np.where(click_map == np.max(click_map))
    else:
      pts = np.where(click_map == 0)
    pts_zipped = zip(pts[0], pts[1])
    if len(pts[0]) > 0:
      for pt in pts_zipped:
        if r < pt[0] < img.shape[0] - r and r < pt[1] < img.shape[1] - r:
          rr, cc = circle(pt[0], pt[1], 5, img.shape)
          img[rr, cc, :] = [np.max(img), np.min(img), np.min(img)] if c == 'r' \
            else [np.min(img), np.min(img), np.max(img)]

    if len(list(img.shape)) == 3:
      img = img[np.newaxis, :, :, :]
    if out_imgs is None:
      out_imgs = img
    else:
      out_imgs = np.concatenate((out_imgs, img), axis = 0)

  return out_imgs.astype(np.float32)


def generate_click_for_correction(label, prediction, previous_clicks, void_label, n_clicks=1, d_step=5):
  prediction = np.copy(prediction).astype(np.uint8)
  label = np.copy(label).astype(np.uint8)

  # Perform opening to separate clusters connected by small structures.
  valid_mask = label != void_label
  misclassified = np.where(label != prediction, 1, 0)
  misclassified *= valid_mask
  # opened = opening(misclassified, disk(2))
  misclassified = skimage_measure.label(misclassified, background=0)
  previous_clicks = [a for a in zip(*(val for val in previous_clicks))]
  misclassified[previous_clicks] = 0

  clicks = []
  clusters = np.setdiff1d(np.unique(misclassified), [0])
  if len(clusters) == 0:
    return clicks

  largest_cluster = np.argmax(np.delete(np.bincount(misclassified.flatten()), 0, axis=0)) + 1

  dt = np.where(misclassified == largest_cluster, 1, 0)
  # dt=misclassified
  # Set the border pixels of the image to 0, so that the click is centred on the required mask.
  dt[[0, dt.shape[0] - 1], :] = 0
  dt[:, [0, dt.shape[1] - 1]] = 0

  dt = distance_transform_edt(dt)

  for i in range(n_clicks):
    row = None
    col = None

    if np.max(dt) > 0:
      # get points that are farthest from the object boundary.
      # farthest_pts = np.where(dt > np.max(dt) / 2.0)
      farthest_pts = np.where(dt == np.max(dt))
      farthest_pts = [x for x in zip(farthest_pts[0], farthest_pts[1])]
      # sample from the list since there could be more that one such points.
      row, col = random.sample(farthest_pts, 1)[0]
      x_min = max(0, row - d_step)
      x_max = min(row + d_step, dt.shape[0])
      y_min = max(0, col - d_step)
      y_max = min(col + d_step, dt.shape[1])
      dt[x_min:x_max, y_min:y_max] = 0

    if row is not None and col is not None:
      clicks.append((row, col))
      dt[row, col] = 0

  return clicks


def normalise_click_maps(dt, use_gaussian):
  dt = dt.astype("float32")
  if use_gaussian:
    dt[dt > 20] = 20
    dt = norm.pdf(dt, loc=0, scale=10) * 25
  else:
    dt[dt > 255] = 255
    dt /= 255.0
  return dt.astype(np.float32)


def normalise_click_maps_tf(dt, use_gaussian):
  if use_gaussian:
    dist = tf.distributions.Normal(loc=0.0, scale=10.0)
    dt = dist.prob(dt)
    dt = tf.where(tf.greater(dt, 20.0), tf.ones_like(dt) * 20.0, dt)
  else:
    dt = tf.where(tf.greater(dt, 255.0), tf.ones_like(dt) * 255.0, dt)
    dt /= 255.0
  return tf.cast(dt, tf.float32)


def unique_list(l):
  res = []
  for x in l:
    if x not in res:
      res.append(x)
  return res


# decode RLE masks
# https://github.com/tylin/coco-caption/blob/master/pycocotools/coco.py
def decodeMask(R):
  """
    Decode binary mask M encoded via run-length encoding.
    :param   R (object RLE)    : run-length encoding of binary mask
    :return: M (bool 2D array) : decoded binary mask
    """
  N = len(R['counts'])
  M = np.zeros((R['size'][0] * R['size'][1],))
  n = 0
  val = 1
  for pos in range(N):
    val = not val
    for c in range(R['counts'][pos]):
      R['counts'][pos]
      M[n] = val
      n += 1
  return M.reshape((R['size']), order='F')


# Encode binary masks to run length encoding (RLE) to save memory.
# https://github.com/tylin/coco-caption/blob/master/pycocotools/coco.py
def encodeMask(M):
  """
    Encode binary mask M using run-length encoding.
    :param   M (bool 2D array)  : binary mask to encode
    :return: R (object RLE)     : run-length encoding of binary mask
    """
  [h, w] = M.shape
  M = M.flatten(order='F')
  N = len(M)
  counts_list = []
  pos = 0
  # counts
  counts_list.append(1)
  diffs = np.logical_xor(M[0:N - 1], M[1:N])
  for diff in diffs:
    if diff:
      pos += 1
      counts_list.append(1)
    else:
      counts_list[pos] += 1
  # if array starts from 1. start with 0 counts for 0
  if M[0] == 1:
    counts_list = [0] + counts_list
  return {'size': [h, w],
          'counts': counts_list,
          }


def get_masked_image(img, mask, multiplier=0.6, dt=None):
  """
  :param img: The image to be masked.
  :param mask: Binary mask to be applied. The object should be represented by 1 and the background by 0
  :param multiplier: Floating point multiplier that decides the colour of the mask.
  :return: Masked image
  """
  img_mask = np.zeros_like(img)
  if dt == DataKeys.UNSIGNED_DISTANCE_TRANSFORM_GUIDANCE:
    indices = np.where(mask == 0)
  elif dt == DataKeys.SIGNED_DISTANCE_TRANSFORM_GUIDANCE:
    indices = np.where(mask < 0)
  else:
    indices = np.where(mask == 1)
  result_img = img
  if len(indices) >= 2:
    img_mask[indices[0], indices[1], 1] = 1
    img_mask_hsv = color.rgb2hsv(img_mask)
    img_hsv = color.rgb2hsv(img)
    img_hsv[indices[0], indices[1], 0] = img_mask_hsv[indices[0], indices[1], 0]
    img_hsv[indices[0], indices[1], 1] = img_mask_hsv[indices[0], indices[1], 1] * multiplier
    result_img = color.hsv2rgb(img_hsv)

  return result_img
