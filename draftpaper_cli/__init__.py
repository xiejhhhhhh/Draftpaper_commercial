"""Local-first CLI workflow for staged research paper projects."""

from .analysis_code import AnalysisCodeGenerationError, generate_analysis_code
from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, inventory_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, write_discussion
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .integrity_gate import IntegrityGateError, latest_integrity_report, run_integrity_gate
from .latex_assembly import LatexAssemblyError, LatexCitationError, assemble_latex, compile_latex_pdf
from .methods import MethodsGateError, verify_methods, write_methods
from .orchestrator import OrchestratorError, checkpoint_project, resume_project, run_pipeline, status_project
from .passport import PassportError, load_project_passport, refresh_project_passport
from .project_scaffold import ProjectAlreadyExistsError, ProjectScaffold, create_project
from .project_state import (
    InvalidStageStatusError,
    ProjectState,
    ProjectStateError,
    UnknownStageError,
    load_project,
    mark_stage_stale,
    update_stage_status,
    validate_project,
)
from .quality_gate import QualityGateError, run_quality_check
from .references import write_reference_outputs
from .research_plan import MissingReferencesError, generate_research_plan
from .review_revision import ReviewRevisionError, apply_revision, diagnose_gate_failures, generate_revision_plan, re_review, review_draft
from .results import ResultsGateError, inventory_results, write_results
from .stale_sync import ArtifactDriftError, detect_artifact_drift, sync_artifact_stale

__all__ = [
    "InvalidStageStatusError",
    "CitationIntegrityError",
    "MissingIntroductionInputsError",
    "MissingDiscussionInputsError",
    "DiscussionCitationIntegrityError",
    "DataGateError",
    "AnalysisCodeGenerationError",
    "ArtifactDriftError",
    "LatexAssemblyError",
    "LatexCitationError",
    "MethodsGateError",
    "OrchestratorError",
    "PassportError",
    "ResultsGateError",
    "ProjectAlreadyExistsError",
    "ProjectScaffold",
    "ProjectState",
    "ProjectStateError",
    "QualityGateError",
    "IntegrityGateError",
    "ReviewRevisionError",
    "UnknownStageError",
    "create_project",
    "load_project",
    "mark_stage_stale",
    "update_stage_status",
    "validate_project",
    "run_quality_check",
    "run_integrity_gate",
    "latest_integrity_report",
    "status_project",
    "checkpoint_project",
    "resume_project",
    "run_pipeline",
    "load_project_passport",
    "refresh_project_passport",
    "detect_artifact_drift",
    "sync_artifact_stale",
    "generate_analysis_code",
    "write_introduction",
    "inventory_data",
    "assess_data_quality",
    "assess_data_feasibility",
    "write_discussion",
    "assemble_latex",
    "compile_latex_pdf",
    "verify_methods",
    "write_methods",
    "inventory_results",
    "write_results",
    "write_reference_outputs",
    "MissingReferencesError",
    "generate_research_plan",
    "diagnose_gate_failures",
    "review_draft",
    "generate_revision_plan",
    "apply_revision",
    "re_review",
]
