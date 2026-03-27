"""Integration tests against live AMI server.

These tests require a valid VOMS proxy and network access to AMI.
Run with: pytest tests/integration/ --runslow -v
"""

from __future__ import annotations

import pyAMI.client
import pyAMI_atlas.api  # noqa: F401
import pytest
from pyAMI_atlas import api


@pytest.mark.slow
def test_ami_execute_searchquery() -> None:
    """ami_execute with a simple SearchQuery returns results."""
    client = pyAMI.client.Client("atlas-replica")
    cmd = (
        'SearchQuery -catalog="mc23_001:production" -entity="HASHTAGS"'
        ' -mql="SELECT DISTINCT `mc23_001:production`.`HASHTAGS`.`NAME`'
        " WHERE `mc23_001:production`.`HASHTAGS`.`SCOPE` = 'PMGL1'"
        ' LIMIT 5"'
    )
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0


@pytest.mark.slow
def test_ami_get_dataset_info_known_dataset() -> None:
    """ami_get_dataset_info returns metadata for a known EVNT dataset."""
    client = pyAMI.client.Client("atlas-replica")
    # mc20 Zee sample — should be stable
    ldn = "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
    rows = api.get_dataset_info(client, ldn)
    assert len(rows) > 0
    row = rows[0]
    assert "logicalDatasetName" in row or "nFiles" in row


@pytest.mark.slow
def test_ami_search_by_hashtags_weakboson() -> None:
    """Searching for WeakBoson/Vjets/Baseline returns mc20 datasets."""
    client = pyAMI.client.Client("atlas-replica")
    cmd = (
        "DatasetWBListDatasetsForHashtag"
        ' -scope="PMGL1,PMGL2,PMGL3"'
        ' -name="WeakBoson,Vjets,Baseline"'
        ' -operator="AND"'
    )
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0
    # Filter to mc20 and verify at least one match
    mc20_rows = [r for r in rows if r.get("ldn", "").startswith("mc20_13TeV.")]
    assert len(mc20_rows) > 0


@pytest.mark.slow
def test_ami_get_physics_params_known_dataset() -> None:
    """GetPhysicsParamsForDataset returns crossSection for a known dataset."""
    client = pyAMI.client.Client("atlas-replica")
    ldn = "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
    cmd = f'GetPhysicsParamsForDataset -logicalDatasetName="{ldn}"'
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0
    assert "crossSection" in rows[0]
