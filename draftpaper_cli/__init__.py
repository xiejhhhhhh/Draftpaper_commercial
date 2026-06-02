"""Local-first CLI workflow for staged research paper projects."""

from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, inventory_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, write_discussion
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .latex_assembly import LatexAssemblyError, LatexCitationError, assemble_latex, compile_latex_pdf
from .methods import MethodsGateError, verify_methods, write_methods
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
from .results import ResultsGateError, inventory_results, write_results

__all__ = [
    "InvalidStageStatusError",
    "CitationIntegrityError",
    "MissingIntroductionInputsError",
    "MissingDiscussionInputsError",
    "DiscussionCitationIntegrityError",
    "DataGateError",
    "LatexAssemblyError",
    "LatexCitationError",
    "MethodsGateError",
    "ResultsGateError",
    "ProjectAlreadyExistsError",
    "ProjectScaffold",
    "ProjectState",
    "ProjectStateError",
    "QualityGateError",
    "UnknownStageError",
    "create_project",
    "load_project",
    "mark_stage_stale",
    "update_stage_status",
    "validate_project",
    "run_quality_check",
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
]
