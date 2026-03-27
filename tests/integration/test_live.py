"""Integration tests against live AMI server.

These tests require a valid VOMS proxy and network access to AMI.
Run with: pytest tests/integration/ --runslow -v
"""

from __future__ import annotations

import pytest


@pytest.mark.slow
def test_ami_execute_searchquery() -> None:
    """ami_execute with a simple SearchQuery returns results."""
    import pyAMI.client
    import pyAMI_atlas.api  # noqa: F401

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
    import pyAMI.client
    import pyAMI_atlas.api as api

    client = pyAMI.client.Client("atlas-replica")
    # mc20 Zee sample — should be stable
    ldn = "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
    rows = api.get_dataset_info(client, ldn)
    assert len(rows) > 0
    row = rows[0]
    assert "logicalDatasetName" in row or "nFiles" in row


@pytest.mark.slow
def test_ami_search_by_hashtags_weakboson() -> None:
    """Searching for WeakBoson/Vjets/Baseline in mc20 returns datasets."""
    import pyAMI.client
    import pyAMI_atlas.api  # noqa: F401

    client = pyAMI.client.Client("atlas-replica")
    cmd = (
        "DatasetWBListDatasetsForHashtag"
        ' -logicalDatasetName="mc20_13TeV.*"'
        ' -PMGL1="WeakBoson" -PMGL2="Vjets" -PMGL3="Baseline"'
    )
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0


@pytest.mark.slow
def test_ami_get_physics_params_known_dataset() -> None:
    """GetPhysicsParamsForDataset returns crossSection for a known dataset."""
    import pyAMI.client
    import pyAMI_atlas.api  # noqa: F401

    client = pyAMI.client.Client("atlas-replica")
    ldn = "mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"
    cmd = f'GetPhysicsParamsForDataset -logicalDatasetName="{ldn}"'
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0
    assert "crossSection" in rows[0]
