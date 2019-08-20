from datasets import DataKeys
from datasets.KITTI.mturkers.KITTI_mturkers_instance import KITTIMturkersInstanceDataset
from datasets.util.Normalization import unnormalize
from datasets.util.Util import visualise_clicks
from scripts.Datasets.EvalPascalMasked import EvalPascalMaskedDataset
import tensorflow as tf

NAME = "eval_kitti_dataset"


class EvalKittiDataset(KITTIMturkersInstanceDataset):
  def __init__(self, config, subset, name=NAME):
    super(EvalKittiDataset, self).__init__(config,subset,name)
    self.eval_pascal_dataset = EvalPascalMaskedDataset(config, subset)
    self.previous_epoch_data = self.eval_pascal_dataset.previous_epoch_data

  def get_extraction_keys(self):
    return self.eval_pascal_dataset.get_extraction_keys()

  def postproc_example_before_assembly(self, tensors):
    return self.eval_pascal_dataset.postproc_example_before_assembly(tensors)

  def use_segmentation_mask(self, res):
    self.eval_pascal_dataset.use_segmentation_mask(res)

  def postproc_annotation(self, ann_filename, ann):
    mask = super().postproc_annotation(ann_filename, ann)
    mask = mask / 255
    return {DataKeys.SEGMENTATION_LABELS: mask, DataKeys.RAW_SEGMENTATION_LABELS: mask,
            DataKeys.IMAGE_FILENAMES: ann_filename}

  def create_summaries(self, data):
    if DataKeys.IMAGES in data:
      images = unnormalize(data[DataKeys.IMAGES])
      if DataKeys.NEG_CLICKS in data:
        images = tf.py_func(visualise_clicks, [images, data[DataKeys.NEG_CLICKS][:, :, :, 0:1], "r"], tf.float32)
        self.summaries.append(tf.summary.image(self.subset + "data/neg_clicks",
                                               tf.cast(data[DataKeys.NEG_CLICKS][:, :, :, 0:1], tf.float32)))
      if DataKeys.POS_CLICKS in data:
        images = tf.py_func(visualise_clicks, [images, data[DataKeys.POS_CLICKS][:, :, :, 0:1], "g"], tf.float32)
        self.summaries.append(tf.summary.image(self.subset + "data/pos_clicks",
                                               tf.cast(data[DataKeys.POS_CLICKS][:, :, :, 0:1], tf.float32)))
      self.summaries.append(tf.summary.image(self.subset + "data/images", images))

    if DataKeys.SEGMENTATION_LABELS in data:
      self.summaries.append(tf.summary.image(self.subset + "data/ground truth segmentation labels",
                                             tf.cast(data[DataKeys.SEGMENTATION_LABELS], tf.float32)))
    if DataKeys.BBOX_GUIDANCE in data:
      self.summaries.append(tf.summary.image(self.subset + "data/bbox guidance",
                                             tf.cast(data[DataKeys.BBOX_GUIDANCE], tf.float32)))
    if DataKeys.SIGNED_DISTANCE_TRANSFORM_GUIDANCE in data:
      self.summaries.append(tf.summary.image(self.subset + "data/signed_distance_transform_guidance",
                                             data[DataKeys.SIGNED_DISTANCE_TRANSFORM_GUIDANCE]))
    if DataKeys.UNSIGNED_DISTANCE_TRANSFORM_GUIDANCE in data:
      self.summaries.append(tf.summary.image(self.subset + "data/unsigned_distance_transform_guidance",
                                             data[DataKeys.UNSIGNED_DISTANCE_TRANSFORM_GUIDANCE]))