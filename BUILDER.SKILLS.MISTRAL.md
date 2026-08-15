# Builder Agent Skills and Capabilities

## Core Competencies

### 1. Migration Planning and Execution
- **Decision Migration GUPs**: Build decision-driven canonical migration packages
- **Identity Merge Migrations**: Handle node ID replacements and retirements
- **Page-Only Corrections**: Process citation-only updates without changing assertion semantics
- **Before-Image Validation**: Ensure exact row state matching for migration planning

### 2. Schema and Validation Expertise
- **GUP Schema Compliance**: Validate against `schemas/common/gup.schema.json` and ruleset-specific schemas
- **Canonical Graph Invariants**: Enforce graph invariants from `contracts/GRAPH_INVARIANTS.md`
- **Validation Report Generation**: Create comprehensive validation reports with error/warning/info classifications
- **Checksum Verification**: SHA-256 checksumming for all artifacts and dependencies

### 3. Test Suite Maintenance
- **Unit Test Development**: Create and maintain comprehensive test suites
- **Regression Testing**: Prevent regression in canonical graph processing
- **Acceptance Test Implementation**: Implement Architect Decision acceptance tests
- **Test Debugging**: Diagnose and fix failing tests due to canonical state changes

### 4. Artifact Production
- **GUP YAML Generation**: Create properly structured Graph Update Patches
- **Edge CSV Output**: Generate accompanying edge CSV files
- **Validation JSON Reports**: Produce machine-readable validation reports
- **Provenance Tracking**: Maintain complete artifact lineage and checksums

## Specialized Tools Developed

### Migration Tools
- **Decision Migration Planner**: Plans migrations from Architect Decisions
- **Node ID Replacement Handler**: Manages retirement and replacement of node identities
- **Citation Correction Engine**: Processes page-only corrections accurately

### Validation Tools
- **Validation Report Generator**: Creates comprehensive validation reports
- **Canonical State Validator**: Verifies canonical graph invariants
- **Duplicate Detection**: Identifies semantic and exact duplicate edges

### Testing Tools
- **Deterministic Planning Tests**: Ensure migration planning is deterministic
- **Regression Test Suite**: 360+ tests covering all Builder functionality
- **Integration State Tests**: Handle tests against live canonical data

## Ruleset-Specific Knowledge

### AD&D 1st Edition (adnd1e)
- **Constitution**: Deep understanding of Constitution 1.7 rules
- **Canonical Structure**: 18-field schema expertise
- **Ontology**: Comprehensive knowledge of adnd1e node types and edge types
- **Registry Management**: Node registry operations and validations

### Workflow Knowledge
- **Artifact Lifecycle**: Complete understanding of `contracts/ARTIFACT_LIFECYCLE.md`
- **Work Queue Management**: Queue derivation and state management per `contracts/WORK_QUEUES.md`
- **Escalation Handling**: Proper escalation package creation and processing

## Problem-Solving Patterns

### Canonical State Drift Resolution
- **Integration Impact Analysis**: Diagnose test failures due to integrated migrations
- **Before-Image Updates**: Update migration tests when canonical state changes
- **Validation State Management**: Handle validation reports for evolving canonical data

### Deterministic Output
- **Byte-Stable Serialization**: Ensure reproducible artifact generation
- **Row Order Consistency**: Maintain deterministic row ordering in outputs
- **Checksum Stability**: Generate consistent checksums for identical inputs

### Error Handling
- **Migration Row Mismatch**: Proper error reporting when canonical rows don't match decision expectations
- **Duplicate Assertion Detection**: Identify and report potential duplicate edges
- **Identity Conflict Resolution**: Escalate ambiguous identity situations appropriately

## Performance Characteristics

### Test Execution
- **Full Suite**: 360 tests in ~16 seconds
- **Individual Test Classes**: Sub-second execution for most test classes
- **Memory Efficiency**: Low memory footprint for large canonical datasets

### Artifact Generation
- **Validation Reports**: Millisecond generation for typical migrations
- **GUP Production**: Fast YAML and CSV serialization
- **Checksum Computation**: Efficient SHA-256 computation for large files

## Quality Assurance

### Validation Coverage
- **Schema Validation**: 100% schema compliance checking
- **Graph Invariant Testing**: Complete invariant validation
- **Regression Protection**: Full test suite prevents functional regressions
- **Checksum Verification**: All artifacts and dependencies are checksummed

### Documentation Standards
- **Clear Commit Messages**: Descriptive, action-oriented commit messages
- **Comprehensive Comments**: Code comments explain non-obvious logic
- **Test Documentation**: Test methods document their acceptance criteria
- **Artifact Provenance**: Complete lineage tracking in all outputs

## Integration Points

### Cross-Role Coordination
- **Architect Decisions**: Consumes approved Architect decisions for migration planning
- **Reviewer Hand-offs**: Produces Reviewer-ready artifacts with complete provenance
- **Integrator Support**: Creates integration-ready bundles with proper checksums
- **Analyst Coordination**: Validates against packet source materials when available

### Tool Chain Integration
- **YAML Processing**: Uses PyYAML for artifact parsing and generation
- **CSV Handling**: Robust CSV parsing for canonical data
- **Path Handling**: Cross-platform path management with pathlib
- **JSON Generation**: Standard library JSON for validation reports