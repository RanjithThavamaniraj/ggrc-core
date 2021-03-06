# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

import unittest

from ggrc import utils


class TestUtilsFunctions(unittest.TestCase):

  @unittest.skip("Audit-scope objects can't be mapped from outside")
  def test_mapping_rules(self):
    """ Test that all mappings go both ways """
    mappings = utils.rules.get_mapping_rules()
    verificationErrors = []

    for object_name, object_mappings in mappings.items():
      for mapping in object_mappings:
        try:
          # If obj A is in obj B mappings, make sure that obj B is also in
          # obj A mappings
          self.assertIn(
              mapping, mappings,
              "- {} is not in the mappings dict".format(mapping)
          )
          self.assertIn(
              object_name, mappings[mapping],
              "{} not found in {} mappings".format(object_name, mapping)
          )
        except AssertionError as e:
          verificationErrors.append(str(e))

    verificationErrors.sort()
    self.assertEqual(verificationErrors, [])

  def test_merge_dict(self):
    dict1 = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2,
                },
            },
        },
    }
    dict2 = {
        "a": {
            "b": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3
        },
        "h": 4
    }
    expected_result = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2,
                },
                "f": {
                    "e": 2,
                },
            },
            "g": 3,
        },
        "h": 4,
    }

    result = utils.merge_dict(dict1, dict2)

    self.assertEqual(result, expected_result)

  def test_merge_dicts(self):
    dict1 = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2
                }
            }
        }
    }
    dict2 = {
        "a": {
            "b": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3
        },
        "h": 4
    }
    dict3 = {
        "a": {
            "eeb": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3
        },
        "h": 4
    }

    result = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2,
                },
                "f": {
                    "e": 2,
                },
            },
            "eeb": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3,
        },
        "h": 4,
    }
    expected_result = utils.merge_dicts(dict1, dict2, dict3)
    self.assertEqual(result, expected_result)

  def test_html_cleaner(self):
    def clean(value):
      return utils.html_cleaner.cleaner(None, value, None, None)

    self.assertEqual(clean("<script>alert(1)</script>"), "alert(1)")

    nested = ("<<script>s<script>c<script>r<script>i<script>p<script>t"
              "<script>>alert(2)<<script>/<script>s<script>c<script>r<script>"
              "i<script>p<script>t<script>>")
    self.assertEqual(clean(nested), "alert(2)")
