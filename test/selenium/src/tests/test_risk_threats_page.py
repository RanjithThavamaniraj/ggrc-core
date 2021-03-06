# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Risks/Threats page smoke tests."""
# pylint: disable=no-self-use
# pylint: disable=invalid-name
# pylint: disable=too-few-public-methods

import pytest    # pylint: disable=import-error

from lib import base
from lib.constants import url


class TestRiskThreatPage(base.Test):
  """Tests the threat/risk page, a part of smoke tests, section 8."""

  @pytest.mark.smoke_tests
  def test_app_redirects_to_new_risk_page(self, new_risk_ui):
    """Tests if after saving and closing the lhn_modal the app redirects to
    the object page.
    Generally we start at a random url. Here we verify that after saving
    and closing the lhn_modal we're redirected to an url that contains an
    object id.
    """
    assert (
        url.RISKS + "/" + new_risk_ui.object_id in new_risk_ui.url)
