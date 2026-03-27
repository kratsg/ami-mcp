"""ATLAS nomenclature and PMG hashtag constants for ami-mcp.

Covers ATLAS dataset naming conventions, PMG hashtag hierarchy, MC campaign
mappings, and the AMI query DSL — all embedded in server instructions and MCP
resources so the LLM can formulate queries without being hand-held.
"""

from __future__ import annotations

#: Full ATLAS nomenclature reference — embedded in server instructions and
#: exposed as the ami://atlas-nomenclature resource.
ATLAS_NOMENCLATURE = """\
ATLAS Dataset Nomenclature — ATL-COM-GEN-2007-003 (2024 edition)

═══════════════════════════════════════════════════════════════
DATA IDENTIFIER (DID / LDN) FORMAT
═══════════════════════════════════════════════════════════════
All ATLAS datasets are identified by a Logical Dataset Name (LDN).
Format:  project.field2.field3.prodStep.dataType.versionTag

  project       ≤ 15 chars — last 2 digits = year or run-period year
                MC:   mc16_13TeV  mc20_13TeV  mc21_13p6TeV  mc23_13p6TeV
                Data: data15_13TeV  data17_13TeV  data18_13TeV
                      data22_13p6TeV  data23_13p6TeV  data24_13p6TeV

  MONTE CARLO:
    project.DSID.physicsShort.prodStep.dataType.versionTag
    Example:
      mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.deriv.DAOD_PHYS.e8351_s3681_r13144_r13146_p5855

    DSID          6-8 digit dataset number (identifies the physics process)
    physicsShort  ≤ 50 chars, human-readable: generator_tune_process
    versionTag    chain of AMI tags: e=evgen s=simul d=digit r=reco p=deriv

  REAL DATA (primary):
    project.runNumber.streamName.prodStep.dataType.versionTag
    Example:
      data18_13TeV.00348885.physics_Main.deriv.DAOD_PHYS.r13286_p4910_p5855

  REAL DATA (physics containers — preferred for analysis):
    project.periodName.streamName.PhysCont.dataType.contVersion
    Example:
      data15_13TeV.periodAllYear.physics_Main.PhysCont.DAOD_PHYSLITE.grp15_v01_p5631

prodStep: evgen→EVNT  simul→HITS  digit→RDO  recon→ESD/AOD  deriv→DAOD_*
dataType: EVNT  HITS  RDO  ESD  AOD  DAOD_PHYS  DAOD_PHYSLITE  DAOD_EXOT*  NTUP
AMI tag letters: e=evgen s=simul d=digit r=reco(ProdSys/Tier0) p=deriv m=merge

═══════════════════════════════════════════════════════════════
PMG HASHTAG SYSTEM (4-level hierarchy)
═══════════════════════════════════════════════════════════════
Hashtags classify MC samples in the ATLAS Production & MC working group.
Each EVNT dataset is tagged with up to 4 levels:

  PMGL1  Physics process subgroup (e.g. WeakBoson, Top, Higgs, Diboson)
  PMGL2  Sample type / process (e.g. Vjets, ttbar, WW)
  PMGL3  Usage classification — one of:
           Baseline      the recommended sample for this process
           Systematic    alternative for systematic variations
           Alternative   another generator choice
           Obsolete      superseded, do not use
           Specialised   specialised production
  PMGL4  Generator detail (e.g. Sherpa_2211, Powheg_Pythia8)

Hashtags are attached to EVNT datasets in AMI via the DatasetWB (Workbook)
interface. The SearchQuery can find all datasets with a given hashtag
combination, and DatasetWBListHashtags can reverse-lookup hashtags for a
given dataset.

═══════════════════════════════════════════════════════════════
MC CAMPAIGNS AND CATALOG MAPPING
═══════════════════════════════════════════════════════════════
Scope (Rucio)    Catalog (AMI evgen)         Description
mc16_13TeV       mc15_001:production         Run 2 (2015-2018)
mc20_13TeV       mc15_001:production         Run 2 reprocessing
mc21_13p6TeV     mc21_001:production         Run 3 pilot
mc23_13p6TeV     mc23_001:production         Run 3

Note: mc16 and mc20 evgen datasets live in the mc15 AMI catalog because they
were generated with mc15-era job options.

Standard physics metadata fields on EVNT datasets:
  crossSection    generator-level cross-section (in nb in AMI; convert x1000 for pb)
  genFiltEff      generator filter efficiency (0-1)
  kFactor         k-factor for NLO/NNLO corrections (typically 1.0 if unknown)

These are accessed via GetPhysicsParamsForDataset or the PMG cross-section DB.
"""

#: AMI query language reference — the key resource enabling the LLM to
#: construct arbitrary AMI queries for ami_execute.
AMI_QUERY_LANGUAGE = """\
AMI Query Language Reference
═══════════════════════════════════════════════════════════════

AMI (ATLAS Metadata Interface) accepts command strings via client.execute().
The primary commands for ATLAS dataset operations are:

═══════════════════════════════════════════════════════════════
MQL GRAMMAR (AMICoreLib/src/main/antlr4/.../MQL.g4)
═══════════════════════════════════════════════════════════════
MQL (Metadata Query Language) is a SQL-like language used in -mql= arguments.

SELECT statement (the only form you need for reads):
  SELECT [DISTINCT] col [, col ...]
    [WHERE expr]
    [GROUP BY col [, col ...]]
    [ORDER BY col [, col ...] [ASC | DESC]]
    [LIMIT n [OFFSET m]]

Identifiers (field/table names) — three quoting forms:
  plain          NAME, SCOPE, logicalDatasetName   (alphanumeric + _ # $)
  backtick       `catalog:name`.`entity`.`field`   (escape literal backtick as ``)
  double-quote   "my field"                         (escape literal " as "")
  Keywords must be quoted if used as names.

String literals: single-quoted  'WeakBoson'  (escape ' as '')

Comparison operators:
  =  !=  <>  ^=  <=>  <  >  <=  >=

Logical operators (case-insensitive; symbol aliases shown):
  AND  (&&)   OR  (||)   XOR  (^^)   NOT

String / pattern operators:
  LIKE     'pattern%'   -- % wildcard, _ single char; NOT LIKE also valid
  REGEXP   'pattern'    -- regular expression match
  BETWEEN  v1 AND v2
  IN       (v1, v2, ...)
  IS NULL  /  IS NOT NULL

Arithmetic: + - * / %

Built-in functions:
  Aggregates:  COUNT(x)  SUM(x)  AVG(x)  MIN(x)  MAX(x)  STDEV(x)
  Math:        ABS  SQRT  POW  LOG  SIN  COS  ROUND  MOD  RAND
  String:      LOWER  UPPER  CONCAT  LENGTH  SUBSTR
  Time:        TIMESTAMP  AMI_TIMESTAMP  AMI_DATE  AMI_TIME
  JSON:        JSON_<key>

LIMIT syntax:  LIMIT 50        -- first 50 rows
               LIMIT 50 OFFSET 200  -- rows 201-250

Comments:  -- this is a comment (to end of line)

═══════════════════════════════════════════════════════════════
SEARCHQUERY — General MQL queries
═══════════════════════════════════════════════════════════════
Syntax:
  SearchQuery -catalog="<catalog>" -entity="<entity>"
              -mql="<mql_select_statement>"

Catalogs:
  mc15_001:production    mc16 + mc20 evgen datasets
  mc21_001:production    mc21 evgen datasets
  mc23_001:production    mc23 evgen datasets

Entities (tables) within a catalog:
  dataset                All datasets
  HASHTAGS               PMG hashtag assignments
  projects               Projects
  files                  Files

Field reference for 'dataset' entity:
  logicalDatasetName    full dataset LDN
  datasetNumber         DSID (integer)
  physicsShort          process description
  amiStatus             VALID, INVALID, etc.
  crossSection          cross-section (nb)
  genFiltEff            filter efficiency
  kFactor               k-factor
  prodsysStatus         production status

  Fully-qualified form (needed when joining):
    `mc15_001:production`.`dataset`.`logicalDatasetName`

Field reference for 'HASHTAGS' entity:
  NAME       hashtag name (e.g. WeakBoson, Vjets, Baseline)
  SCOPE      level: PMGL1 / PMGL2 / PMGL3 / PMGL4
  fullname   fully qualified name
  comment    description
  (No LDN field — HASHTAGS stores tag definitions, not dataset assignments.
   Use DatasetWBListDatasetsForHashtag to find datasets by hashtag combination.)

Examples:
  # List all PMGL1 hashtag names in mc23:
  SearchQuery -catalog="mc23_001:production" -entity="HASHTAGS"
    -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL1'"

  # List PMGL3 status values (Baseline / Systematic / Alternative / ...):
  # Note: HASHTAGS entity only works in mc21_001 and mc23_001 catalogs,
  # NOT in mc15_001:production (returns a parse error).
  SearchQuery -catalog="mc23_001:production" -entity="HASHTAGS"
    -mql="SELECT DISTINCT NAME WHERE SCOPE = 'PMGL3'"

  # Search for Zee datasets in mc20 (filter on physicsShort, not logicalDatasetName):
  # Note: LIKE on logicalDatasetName in mc15_001 catalog causes parse errors.
  # Use physicsShort LIKE for dataset name patterns in mc15_001.
  SearchQuery -catalog="mc15_001:production" -entity="dataset"
    -mql="SELECT logicalDatasetName, crossSection, genFiltEff
          WHERE physicsShort LIKE '%Zee%'
          AND amiStatus = 'VALID'
          LIMIT 50"

  # For multi-level hashtag filtering (WeakBoson/Vjets/Baseline), use
  # DatasetWBListDatasetsForHashtag (see below) or the ami_search_by_hashtags tool.
  # Note: DatasetWBListDatasetsForHashtag only covers mc21 and mc23 datasets;
  # mc20/mc16 datasets are not indexed in the hashtag workbook.

═══════════════════════════════════════════════════════════════
DATASETWORKBOOK COMMANDS
═══════════════════════════════════════════════════════════════

DatasetWBListDatasetsForHashtag — find all datasets with a given hashtag combo
  Required: -scope="<levels>"   comma-separated levels, e.g. "PMGL1,PMGL2,PMGL3"
            -name="<names>"     comma-separated hashtag names (same order as scope)
            -operator="AND"     logical combination (AND is standard)
  Returns rows with field: ldn  (the full Logical Dataset Name)
  Note: returns datasets from ALL campaigns — filter the ldn field client-side
        to restrict to a specific campaign (e.g. starts with "mc20_13TeV.")
  Example:
    DatasetWBListDatasetsForHashtag
      -scope="PMGL1,PMGL2,PMGL3"
      -name="WeakBoson,Vjets,Baseline"
      -operator="AND"

DatasetWBListHashtags — reverse-lookup: find hashtags for a given dataset
  Required: -ldn="<full_ldn>"
  Returns rows with fields: scope (PMGL1/PMGL2/...), name (hashtag value)
  Example:
    DatasetWBListHashtags
      -ldn="mc20_13TeV.700320.Sh_2211_Zee_maxHTpTV2_BFilter.evgen.EVNT.e8351"

═══════════════════════════════════════════════════════════════
DATASET INFO COMMANDS
═══════════════════════════════════════════════════════════════

AMIGetDatasetInfo — get full dataset metadata
  Required: -logicalDatasetName="<ldn>"
  Returns: nFiles, nEvents, totalSize, crossSection, genFiltEff, etc.

GetPhysicsParamsForDataset — get physics parameters
  Required: -logicalDatasetName="<ldn>"
  Returns: crossSection (nb), genFiltEff, kFactor, contactPerson, etc.

AMIGetDatasetProv — get dataset provenance (parent/child chain)
  Required: -logicalDatasetName="<ldn>"

AMIGetAMITagInfo — get information about an AMI processing tag
  Required: -amiTag="<tag>"
  Example: -amiTag="e8351"

═══════════════════════════════════════════════════════════════
RESULT FORMAT
═══════════════════════════════════════════════════════════════
All commands return a DOMObject. Call .get_rows() to get a list of OrderedDicts,
or .get_rows('<row_type>') for specific row types (e.g. 'node', 'edge' for prov).
"""

#: PMG cross-section database format reference — for the xsec DB tools.
PMG_XSEC_DATABASE = """\
PMG Cross-Section Database Reference
═══════════════════════════════════════════════════════════════

The PMG cross-section database files are the authoritative source for
cross-sections, filter efficiencies, and k-factors used by ATLAS analysers.

Location:
  /cvmfs/atlas.cern.ch/repo/sw/database/GroupData/dev/PMGTools/PMGxsecDB_*.txt
  (also mirrored at /eos/atlas/atlascerngroupdisk/asg-calib/dev/PMGTools/)

File naming convention:
  PMGxsecDB_mc16.txt    mc16 + mc20 samples (Run 2)
  PMGxsecDB_mc23.txt    mc23 samples (Run 3)
  (other files for mc15, mc21, etc. may also be present)

File format (tab-separated values):
  - First line: header defining column names and types
    Format: colName/TYPE:colName/TYPE:...
    Types: /I = integer, /C = string, /D = float
  - Subsequent lines: data rows

Columns (newer mc16/mc21/mc23 files):
  dataset_number/I    DSID (integer)
  physics_short/C     process description (physicsShort)
  crossSection_pb/D   cross-section in picobarn (pb)
  genFiltEff/D        generator filter efficiency (0.0-1.0)
  kFactor/D           k-factor for NLO/NNLO corrections
  relUncertUP/D       relative uncertainty up (fraction, e.g. 0.05 = 5%)
  relUncertDOWN/D     relative uncertainty down (fraction)
  generator_name/C    generator name string
  etag/C              evgen AMI tag (e.g. "e8351")

Note on units:
  Newer files (mc16, mc21, mc23): crossSection_pb column is already in pb.
  Older files (mc15): column is named crossSection and is in nb (x1000 = pb).

Multiple rows per DSID:
  A DSID may appear multiple times with different etags (different generator
  versions or configurations). The etag uniquely identifies the row.

The DSID+etag combination uniquely identifies a cross-section entry.
"""
