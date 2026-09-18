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


@pytest.mark.slow
def test_ami_list_datasets_finds_mc20_derivations_in_mc20_catalog() -> None:
    """The #24 repro: mc20_13TeV DAOD_PHYS Zee datasets live in mc20_001, not mc15.

    ami_list_datasets picks this catalog via scope_to_catalog("mc20_13TeV",
    data_type_to_prod_step("DAOD_PHYS")) == "mc20_001:production" -- confirm
    the catalog and projectName combination actually has rows in AMI.
    """
    client = pyAMI.client.Client("atlas-replica")
    mql = (
        "SELECT logicalDatasetName, physicsShort, amiStatus"
        " WHERE physicsShort LIKE '%Zee%' AND projectName = 'mc20_13TeV'"
        " AND dataType = 'DAOD_PHYS' LIMIT 0,5"
    )
    cmd = f'SearchQuery -catalog=mc20_001:production -entity=dataset -mql="{mql}"'
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0


@pytest.mark.slow
def test_ami_list_datasets_finds_mc20_evgen_in_mc15_catalog() -> None:
    """Confirms the mc15 evgen-catalog branch: mc20_13TeV EVNT lives in mc15_001.

    Companion to the mc20 derivation test above -- if this one fails, the
    evgen special case in the scope_to_catalog table is dead weight for
    ami_list_datasets and should collapse to the project's own prefix.
    """
    client = pyAMI.client.Client("atlas-replica")
    mql = (
        "SELECT logicalDatasetName, physicsShort, amiStatus"
        " WHERE physicsShort LIKE '%Zee%' AND projectName = 'mc20_13TeV'"
        " AND dataType = 'EVNT' LIMIT 0,5"
    )
    cmd = f'SearchQuery -catalog=mc15_001:production -entity=dataset -mql="{mql}"'
    result = client.execute(cmd, format="dom_object")
    rows = result.get_rows()
    assert len(rows) > 0
