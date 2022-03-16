#!/usr/bin/env python3

################################################
#
#   create_metawfr
#
################################################

################################################
#   Libraries
################################################
import datetime
import json
import uuid

from dcicutils import ff_utils

# magma
from magma_ff.metawfl import MetaWorkflow
from magma_ff.metawflrun import MetaWorkflowRun
from magma_ff.utils import make_embed_request

################################################
#   MetaWorkflowRunCreationError
################################################
class MetaWorkflowRunCreationError(Exception):
    """Custom exception for error tracking.
    """

################################################
#   MetaWorkflowRunFromSampleProcessing
################################################
class MetaWorkflowRunFromSampleProcessing:
    """Class to create and POST|PATCH to portal a MetaWorkflowRun[json]
    from a SampleProcessing[portal] and a MetaWorkflow[portal].
    """

    # Embedding API fields
    FIELDS_TO_GET = [
        "project",
        "institution",
        "uuid",
        "meta_workflow_runs",
        "samples_pedigree",
        "samples.bam_sample_id",
        "samples.uuid",
        "samples.files.uuid",
        "samples.files.related_files",
        "samples.files.paired_end",
        "samples.files.file_format.file_format",
        "samples.cram_files.uuid",
        "samples.processed_files.uuid",
        "samples.processed_files.file_format.file_format",
    ]

    # Schema constants
    META_WORKFLOW_RUNS = "meta_workflow_runs"
    ASSOCIATED_META_WORKFLOW_RUN = "associated_meta_workflow_run"
    PROJECT = "project"
    INSTITUTION = "institution"
    UUID = "uuid"
    META_WORKFLOW = "meta_workflow"
    FINAL_STATUS = "final_status"
    PENDING = "pending"
    WORKFLOW_RUNS = "workflow_runs"
    TITLE = "title"
    INPUT = "input"
    COMMON_FIELDS = "common_fields"
    INPUT_SAMPLES = "input_samples"
    ASSOCIATED_SAMPLE_PROCESSING = "associated_sample_processing"
    FILES = "files"

    # Class constants
    META_WORKFLOW_RUN_ENDPOINT = "meta-workflow-runs"

    def __init__(
        self,
        sample_processing_identifier,
        meta_workflow_identifier,
        auth_key,
        expect_family_structure=True,
    ):
        """Initialize the object and set all attributes.

        :param sample_processing_identifier: SampleProcessing[portal] UUID
            or @id
        :type sample_processing_identifier: str
        :param meta_workflow_identifier: MetaWorkflow[portal] UUID,
            @id, or accession
        :type meta_workflow_identifier: str
        :param auth_key: Portal authorization key
        :type auth_key: dict
        :param expect_family_structure: Whether a family structure is
            expected on the SampleProcessing[portal]
        :type expect_family_structure: bool
        :raises MetaWorkflowRunCreationError: If required item cannot
            be found on environment of authorization key
        """
        self.auth_key = auth_key
        sample_processing = make_embed_request(
            sample_processing_identifier,
            self.FIELDS_TO_GET,
            self.auth_key,
            single_item=True,
        )
        if not sample_processing:
            raise MetaWorkflowRunCreationError(
                "No SampleProcessing found for given identifier: %s"
                % sample_processing_identifier
            )
        self.meta_workflow = self.get_item_properties(meta_workflow_identifier)
        if not self.meta_workflow:
            raise MetaWorkflowRunCreationError(
                "No MetaWorkflow found for given identifier: %s"
                % meta_workflow_identifier
            )
        self.project = sample_processing.get(self.PROJECT)
        self.institution = sample_processing.get(self.INSTITUTION)
        self.sample_processing_uuid = sample_processing.get(self.UUID)
        self.existing_meta_workflow_runs = sample_processing.get(
            self.META_WORKFLOW_RUNS, []
        )
        self.input_properties = InputPropertiesFromSampleProcessing(
            sample_processing, expect_family_structure=expect_family_structure
        )
        self.meta_workflow_run_input = MetaWorkflowRunInput(
            self.meta_workflow, self.input_properties
        ).create_input()
        self.meta_workflow_run_uuid = str(uuid.uuid4())
        self.meta_workflow_run = self.create_meta_workflow_run()

    def create_meta_workflow_run(self):
        """Create MetaWorkflowRun[json] to later POST to portal.

        :return: MetaWorkflowRun[json]
        :rtype: dict
        """
        meta_workflow_title = self.meta_workflow.get(self.TITLE)
        creation_date = datetime.date.today().isoformat()
        title = "MetaWorkflowRun %s from %s" % (
            meta_workflow_title,
            creation_date,
        )
        meta_workflow_run = {
            self.META_WORKFLOW: self.meta_workflow.get(self.UUID),
            self.INPUT: self.meta_workflow_run_input,
            self.TITLE: title,
            self.PROJECT: self.project,
            self.INSTITUTION: self.institution,
            self.INPUT_SAMPLES: self.input_properties.input_sample_uuids,
            self.ASSOCIATED_SAMPLE_PROCESSING: self.sample_processing_uuid,
            self.COMMON_FIELDS: {
                self.PROJECT: self.project,
                self.INSTITUTION: self.institution,
                self.ASSOCIATED_META_WORKFLOW_RUN: self.meta_workflow_run_uuid,
            },
            self.FINAL_STATUS: self.PENDING,
            self.WORKFLOW_RUNS: [],
            self.UUID: self.meta_workflow_run_uuid,
        }
        self.create_workflow_runs(meta_workflow_run)
        return meta_workflow_run

    def create_workflow_runs(self, meta_workflow_run):
        """Create shards and update MetaWorkflowRun[json].

        :param meta_workflow_run: MetaWorkflowRun[json]
        :type meta_workflow_run: dict
        :raises MetaWorkflowRunCreationError: If input files to
            MetaWorkflowRun cannot be identified
        """
        reformatted_file_input = None
        reformatted_meta_workflow_run = MetaWorkflowRun(meta_workflow_run).to_json()
        reformatted_input = reformatted_meta_workflow_run[self.INPUT]
        for input_item in reformatted_input:
            input_files = input_item.get(self.FILES)
            if input_files is None:
                continue
            reformatted_file_input = input_files
            break
        if reformatted_file_input is None:
            raise MetaWorkflowRunCreationError(
                "No input files were provided for the MetaWorkflowRun: %s"
                % meta_workflow_run
            )
        run_with_workflows = MetaWorkflow(self.meta_workflow).write_run(
            reformatted_file_input
        )
        meta_workflow_run[self.WORKFLOW_RUNS] = run_with_workflows[self.WORKFLOW_RUNS]

    def get_item_properties(self, item_identifier):
        """Retrieve item from given environment without raising
        exception if not found.

        :param item_identifier: Item identifier on the portal
        :type item_identifier: str
        :return: Raw view of item if found
        :rtype: dict or None
        """
        try:
            result = ff_utils.get_metadata(
                item_identifier, key=self.auth_key, add_on="frame=raw"
            )
        except Exception:
            result = None
        return result

    def post_and_patch(self):
        """POST MetaWorkflowRun[json] and PATCH SampleProcessing[portal]
        to update list of its linked MetaWorkflowRun[portal].
        """
        self.post_meta_workflow_run()
        self.patch_sample_processing()

    def post_meta_workflow_run(self):
        """POST MetaWorkflowRun[json] to portal."""
        try:
            ff_utils.post_metadata(
                self.meta_workflow_run,
                self.META_WORKFLOW_RUN_ENDPOINT,
                key=self.auth_key,
            )
        except Exception as error_msg:
            raise MetaWorkflowRunCreationError(
                "MetaWorkflowRun not POSTed: \n%s" % str(error_msg)
            )

    def patch_sample_processing(self):
        """PATCH SampleProcessing[portal]
        to link the new MetaWorkflowRun[portal].

        Note: Method will fail unless MetaWorkflowRun[json] previously
        POSTed.
        """
        meta_workflow_runs = [
            identifier for identifier in self.existing_meta_workflow_runs
        ]
        meta_workflow_runs.append(self.meta_workflow_run_uuid)
        patch_body = {self.META_WORKFLOW_RUNS: meta_workflow_runs}
        try:
            ff_utils.patch_metadata(
                patch_body, obj_id=self.sample_processing_uuid, key=self.auth_key
            )
        except Exception as error_msg:
            raise MetaWorkflowRunCreationError(
                "SampleProcessing could not be PATCHed: \n%s" % str(error_msg)
            )

################################################
#   MetaWorkflowRunInput
################################################
class MetaWorkflowRunInput:
    """Generate MetaWorkflowRun[json] input given MetaWorkflow[json] and
    input properties object with required input fields.
    """

    # Schema constants
    ARGUMENT_NAME = "argument_name"
    ARGUMENT_TYPE = "argument_type"
    VALUE = "value"
    VALUE_TYPE = "value_type"
    FILE = "file"
    FILES = "files"
    PARAMETER = "parameter"
    DIMENSION = "dimension"
    DIMENSIONALITY = "dimensionality"
    INPUT = "input"
    UUID = "uuid"

    def __init__(self, meta_workflow, input_properties):
        """Initialize the object and set all attributes.

        :param meta_workflow: MetaWorkflow[json]
        :type meta_workflow: dict
        :param input_properties: Object containing expected input
            parameters for MetaWorkflow[json]
        :type input_properties: object
        """
        self.meta_workflow = meta_workflow
        self.input_properties = input_properties

    def create_input(self):
        """Create MetaWorkflowRun[json] input based on arguments specified in
        MetaWorkflow[json].

        :return: MetaWorkflowRun[json] input
        :rtype: dict
        :raises MetaWorkflowRunCreationError: If input argument provided
            from MetaWorkflow could not be handled
        """
        result = []
        input_files_to_fetch = []
        input_parameters_to_fetch = []
        input_files = []
        input_parameters = []
        meta_workflow_input = self.meta_workflow.get(self.INPUT, [])
        for input_arg in meta_workflow_input:
            if self.FILES in input_arg or self.VALUE in input_arg:
                continue
            input_arg_name = input_arg.get(self.ARGUMENT_NAME)
            input_arg_type = input_arg.get(self.ARGUMENT_TYPE)
            if input_arg_type == self.FILE:
                input_arg_dimensions = input_arg.get(self.DIMENSIONALITY)
                input_files_to_fetch.append((input_arg_name, input_arg_dimensions))
            elif input_arg_type == self.PARAMETER:
                parameter_value_type = input_arg.get(self.VALUE_TYPE)
                input_parameters_to_fetch.append((input_arg_name, parameter_value_type))
            else:
                raise MetaWorkflowRunCreationError(
                    "Found an unexpected MetaWorkflow input argument type (%s) for"
                    " MetaWorkflow with uuid: %s"
                    % (input_arg_type, self.meta_workflow.get(self.UUID))
                )
        if input_parameters_to_fetch:
            input_parameters = self.fetch_parameters(input_parameters_to_fetch)
            result += input_parameters
        if input_files_to_fetch:
            input_files = self.fetch_files(input_files_to_fetch)
            result += input_files
        return result

    def fetch_files(self, files_to_fetch):
        """Create file inputs for MetaWorkflowRun[json].

        :param files_to_fetch: File input arguments from MetaWorkflow[json]
        :type files_to_fetch: list((str, int))
        :return: Structured file input for MetaWorkflowRun[json]
        :rtype: list(dict)
        :raises MetaWorkflowRunCreationError: If file input argument name
            from MetaWorkflow could not be found on the input properties
            class
        """
        result = []
        for file_parameter, input_dimensions in files_to_fetch:
            try:
                file_parameter_value = getattr(
                    self.input_properties, file_parameter.lower()
                )
            except AttributeError:
                raise MetaWorkflowRunCreationError(
                    "Could not find input parameter: %s" % file_parameter
                )
            formatted_file_value = self.format_file_input_value(
                file_parameter, file_parameter_value, input_dimensions
            )
            file_parameter_result = {
                self.ARGUMENT_NAME: file_parameter,
                self.ARGUMENT_TYPE: self.FILE,
                self.FILES: formatted_file_value,
            }
            result.append(file_parameter_result)
        return result

    def format_file_input_value(self, file_parameter, file_value, input_dimensions):
        """Create one structured file input for MetaWorkflowRun[json].

        :param file_parameter: Name of file input argument
        :type file_parameter: str
        :param file_value: File input values by associated sample
            index, e.g. {1: ["foo"], 0: ["bar"]} has ["foo"] files for
            sample of index 1
        :type file_value: dict
        :param input_dimensions: The number of dimensions to use for
            the given file parameter
        :type input_dimensions: int
        :return: Structured file argument input
        :rtype: dict
        :raises MetaWorkflowRunCreationError: If expected dimensions
            could not be handled or an input of dimension 1 has more
            than 1 entry per sample (i.e. is 2 dimensional)
        """
        result = []
        sorted_key_indices_by_sample = sorted(file_value.keys())
        for sample_idx in sorted_key_indices_by_sample:
            sample_file_uuids = file_value[sample_idx]
            if input_dimensions == 1:
                if len(sample_file_uuids) > 1:
                    raise MetaWorkflowRunCreationError(
                        "Found multiple input files when only 1 was expected for"
                        " parameter %s: %s" % (file_parameter, sample_file_uuids)
                    )
                for file_uuid in sample_file_uuids:
                    dimension = str(sample_idx)
                    formatted_file_result = {
                        self.FILE: file_uuid,
                        self.DIMENSION: dimension,
                    }
                    result.append(formatted_file_result)
            elif input_dimensions == 2:
                for file_uuid_idx, file_uuid in enumerate(sample_file_uuids):
                    dimension = "%s,%s" % (sample_idx, file_uuid_idx)
                    formatted_file_result = {
                        self.FILE: file_uuid,
                        self.DIMENSION: dimension,
                    }
                    result.append(formatted_file_result)
            else:
                raise MetaWorkflowRunCreationError(
                    "Received an unexpected dimension number for parameter %s: %s"
                    % (file_parameter, input_dimensions)
                )
        return result

    def fetch_parameters(self, parameters_to_fetch):
        """Create non-file parameters for MetaWorkflowRun[json].

        :param parameters_to_fetch: Non-file input parameters from
            MetaWorkflow[json]
        :type parameters_to_fetch: list((str, str))
        :return: Structured non-file input
        :rtype: list(dict)
        :raises MetaWorkflowRunCreationError: If given parameter could
            not be found on the input properties class
        """
        result = []
        for parameter, value_type in parameters_to_fetch:
            try:
                parameter_value = getattr(self.input_properties, parameter.lower())
            except AttributeError:
                raise MetaWorkflowRunCreationError(
                    "Could not find input parameter: %s" % parameter
                )
            parameter_value = self.cast_parameter_value(parameter_value)
            parameter_result = {
                self.ARGUMENT_NAME: parameter,
                self.ARGUMENT_TYPE: self.PARAMETER,
                self.VALUE: parameter_value,
                self.VALUE_TYPE: value_type,
            }
            result.append(parameter_result)
        return result

    def cast_parameter_value(self, parameter_value):
        """Cast parameter value in expected format based on value
        type.

        :param parameter_value: Value for a given input parameter
        :type parameter_value: object
        :return: Possibly JSON-formatted string representation of the
            value
        :rtype: str
        """
        if isinstance(parameter_value, list) or isinstance(parameter_value, dict):
            result = json.dumps(parameter_value)
        else:
            result = str(parameter_value)
        return result

################################################
#   InputPropertiesFromSampleProcessing
################################################
class InputPropertiesFromSampleProcessing:
    """Class for accessing MetaWorkflowRun[json] input arguments from a
    SampleProcessing[json].
    """

    # Schema constants
    UUID = "uuid"
    SAMPLES_PEDIGREE = "samples_pedigree"
    SAMPLES = "samples"
    BAM_SAMPLE_ID = "bam_sample_id"
    PROCESSED_FILES = "processed_files"
    FILES = "files"
    CRAM_FILES = "cram_files"
    RELATED_FILES = "related_files"
    FILE_FORMAT = "file_format"
    PAIRED_END = "paired_end"
    PAIRED_END_1 = "1"
    PAIRED_END_2 = "2"
    RELATIONSHIP = "relationship"
    PROBAND = "proband"
    MOTHER = "mother"
    FATHER = "father"
    INDIVIDUAL = "individual"
    PARENTS = "parents"
    SAMPLE_NAME = "sample_name"
    SEX = "sex"

    # File formats
    FASTQ_FORMAT = "fastq"
    CRAM_FORMAT = "cram"
    BAM_FORMAT = "bam"
    GVCF_FORMAT = "gvcf_gz"

    # Class constants
    GENDER = "gender"
    RCKTAR_FILE_ENDING = ".rck.gz"

    def __init__(self, sample_processing, expect_family_structure=True):
        """Initialize the object and set attributes.

        :param sample_processing: SampleProcessing[json]
        :type sample_processing: dict
        :param expect_family_structure: Whether a family structure is
            expected on the SampleProcessing, which influences whether
            the Samples are sorted and cleaning of sample pedigree
        :type expect_family_structure: bool
        """
        self.sample_processing = sample_processing
        (
            self.sorted_samples,
            self.sorted_samples_pedigree,
        ) = self.clean_and_sort_samples_and_pedigree(expect_family_structure)

    def clean_and_sort_samples_and_pedigree(self, expect_family_structure):
        """Sort Samples and pedigree and remove parents from pedigree
        if not included in Samples.

        If not expecting a family structure (such as with a Cohort),
        then Samples and pedigree returned unsorted.

        Sorting order will be proband, then mother, then father, as
        applicable.

        :return: Sorted Samples and sorted/cleaned pedigree
        :rtype: (list(dict), list(dict))
        :raises MetaWorkflowRunCreationError: If Samples or pedigree
            not found, of different lengths, or lack required properties
        """
        proband_name = None
        mother_name = None
        father_name = None
        samples_pedigree = self.sample_processing.get(self.SAMPLES_PEDIGREE, [])
        if not samples_pedigree and expect_family_structure:
            raise MetaWorkflowRunCreationError(
                "No samples_pedigree found on SampleProcessing: %s"
                % self.sample_processing
            )
        samples = self.sample_processing.get(self.SAMPLES, [])
        if not samples:
            raise MetaWorkflowRunCreationError(
                "No Samples found on SampleProcessing: %s" % self.sample_processing
            )
        if expect_family_structure and len(samples) != len(samples_pedigree):
            raise MetaWorkflowRunCreationError(
                "Number of Samples did not match number of entries in samples_pedigree"
                " on SampleProcessing: %s" % self.sample_processing
            )
        all_individuals = [
            sample.get(self.INDIVIDUAL)
            for sample in samples_pedigree
            if sample.get(self.INDIVIDUAL)
        ]
        bam_sample_ids = [
            sample.get(self.BAM_SAMPLE_ID)
            for sample in samples
            if sample.get(self.BAM_SAMPLE_ID)
        ]
        if samples_pedigree and expect_family_structure:
            for pedigree_sample in samples_pedigree:
                parents = pedigree_sample.get(self.PARENTS, [])
                if parents:  # Remove parents that aren't in samples_pedigree
                    missing_parents = [
                        parent for parent in parents if parent not in all_individuals
                    ]
                    for missing_parent in missing_parents:
                        parents.remove(missing_parent)
                sample_name = pedigree_sample.get(self.SAMPLE_NAME)
                if sample_name is None:
                    raise MetaWorkflowRunCreationError(
                        "No sample name given for sample in pedigree: %s"
                        % pedigree_sample
                    )
                elif sample_name not in bam_sample_ids:
                    raise MetaWorkflowRunCreationError(
                        "Sample in pedigree not found on SampleProcessing: %s"
                        % sample_name
                    )
                sex = pedigree_sample.get(self.SEX)
                if sex is None:
                    raise MetaWorkflowRunCreationError(
                        "No sex given for sample in pedigree: %s" % pedigree_sample
                    )
                relationship = pedigree_sample.get(self.RELATIONSHIP)
                if relationship == self.PROBAND:
                    proband_name = sample_name
                elif relationship == self.MOTHER:
                    mother_name = sample_name
                elif relationship == self.FATHER:
                    father_name = sample_name
            if proband_name is None:
                raise MetaWorkflowRunCreationError(
                    "No proband found within the pedigree: %s" % samples_pedigree
                )
            result_samples_pedigree = self.sort_by_sample_name(
                samples_pedigree,
                self.SAMPLE_NAME,
                proband_name,
                mother=mother_name,
                father=father_name,
            )
            result_samples = self.sort_by_sample_name(
                samples,
                self.BAM_SAMPLE_ID,
                proband_name,
                mother=mother_name,
                father=father_name,
            )
        else:
            result_samples = samples
            result_samples_pedigree = samples_pedigree
        return result_samples, result_samples_pedigree

    def sort_by_sample_name(
        self, items_to_sort, sample_name_key, proband, mother=None, father=None
    ):
        """Sort items to be proband, mother, father, then other family
        members, as applicable.

        :param items_to_sort: Items to sort
        :type items_to_sort: list(dict)
        :param sample_name_key: Key of the item dict corresponding to
            sample name of the item
        :type sample_name_key: str
        :param proband: Proband sample name
        :type proband: str
        :param mother: Mother sample name
        :type mother: str or None
        :param father: Father sample name
        :type father: str or None
        :return: Sorted items
        :rtype: list(dict)
        """
        result = []
        other_idx = []
        proband_idx = None
        mother_idx = None
        father_idx = None
        for idx, item in enumerate(items_to_sort):
            sample_name = item.get(sample_name_key)
            if sample_name == proband:
                proband_idx = idx
            elif mother and sample_name == mother:
                mother_idx = idx
            elif father and sample_name == father:
                father_idx = idx
            else:
                other_idx.append(idx)
        if proband_idx is not None:
            result.append(items_to_sort[proband_idx])
        if mother_idx is not None:
            result.append(items_to_sort[mother_idx])
        if father_idx is not None:
            result.append(items_to_sort[father_idx])
        for idx in other_idx:
            result.append(items_to_sort[idx])
        return result

    def get_samples_processed_file_for_format(self, file_format):
        """Grab files of given format from processed_files property for
        each Sample on the SampleProcessing[portal].

        Result is formatted to match expectations of
        MetaWorkflowRunFromInput class.

        :param file_format: File format of files to grab from each
            Sample.processed_files
        :type file_format: str
        :return: Files matching the given format for each Sample
        :rtype: dict
        """
        result = {}
        for idx, sample in enumerate(self.sorted_samples):
            matching_files = self.get_processed_file_for_format(sample, file_format)
            result[idx] = matching_files
        return result

    def get_processed_file_for_format(self, sample, file_format, requirements=None):
        """Get all files matching given file format on given sample
        that meet the given requirements.

        :param sample: Sample properties
        :type sample: dict
        :param file_format: Format of files to get
        :type file_format: str
        :param requirements: Requirements a file must meet in order to
            be acceptable, as key, value pairs of property names, lists
            of acceptable property values
        :type requirements: dict
        :return: Processed file UUIDs of files meeting file format and
            requirements
        :rtype: list(str)
        :raises MetaWorkflowRunCreationError: If no files found to meet
            file format/other requirements
        """
        result = []
        processed_files = sample.get(self.PROCESSED_FILES, [])
        for processed_file in processed_files:
            requirements_met = True
            if requirements:
                for key, accepted_values in requirements.items():
                    key_value = processed_file.get(key)
                    if key_value not in accepted_values:
                        requirements_met = False
                        break
            if requirements_met is False:
                continue
            processed_file_format = processed_file.get(self.FILE_FORMAT, {}).get(
                self.FILE_FORMAT
            )
            if processed_file_format == file_format:
                file_uuid = processed_file.get(self.UUID)
                result.append(file_uuid)
        if not result:
            raise MetaWorkflowRunCreationError(
                "No file with format %s found on Sample: %s" % (file_format, sample)
            )
        return result

    def get_fastqs_for_paired_end(self, paired_end):
        """Get FASTQ files on Sample for given paired end.

        Searches for files first under Sample.files and then, if no
        matches found there, under Sample.processed_files.

        :param paired_end: Desired paired end for FASTQs
        :type paired_end: str
        :return: FASTQ file UUIDs of matching paired end
        :rtype: list(str)
        :raises MetaWorkflowRunCreationError: If FASTQ file without
            related_files property found or no FASTQ files of matching
            paired end found
        """
        result = {}
        for idx, sample in enumerate(self.sorted_samples):
            paired_end_fastqs = []
            fastq_files = sample.get(self.FILES, [])
            for fastq_file in fastq_files:  # Expecting only FASTQs, but check
                file_format = fastq_file.get(self.FILE_FORMAT, {}).get(self.FILE_FORMAT)
                if file_format != self.FASTQ_FORMAT:
                    continue
                related_files = fastq_file.get(self.RELATED_FILES)
                if related_files is None:
                    raise MetaWorkflowRunCreationError(
                        "Sample contains a FASTQ file without a related file: %s"
                        % sample
                    )
                file_paired_end = fastq_file.get(self.PAIRED_END)
                if file_paired_end == paired_end:
                    file_uuid = fastq_file.get(self.UUID)
                    paired_end_fastqs.append(file_uuid)
            if not paired_end_fastqs:  # May have come from CRAM conversion
                requirements = {self.PAIRED_END: [paired_end]}
                paired_end_fastqs = self.get_processed_file_for_format(
                    sample, self.FASTQ_FORMAT, requirements=requirements
                )
            result[idx] = paired_end_fastqs
        return result

    @property
    def sample_names(self):
        """Sorted Sample name input.
        """
        return [sample[self.BAM_SAMPLE_ID] for sample in self.sorted_samples]

    @property
    def input_sample_uuids(self):
        """Sorted Sample UUID input.
        """
        return [sample[self.UUID] for sample in self.sorted_samples]

    @property
    def pedigree(self):
        """Sorted pedigree input.
        """
        result = []
        for pedigree_sample in self.sorted_samples_pedigree:
            result.append(
                {
                    self.PARENTS: pedigree_sample.get(self.PARENTS, []),
                    self.INDIVIDUAL: pedigree_sample.get(self.INDIVIDUAL, ""),
                    self.SAMPLE_NAME: pedigree_sample.get(self.SAMPLE_NAME),
                    # May want to switch gender key to sex below
                    self.GENDER: pedigree_sample.get(self.SEX),
                }
            )
        return result

    @property
    def input_crams(self):
        """Get CRAM files for each Sample.

        :return: CRAM UUIDs for all CRAM files found on all Samples
        :rtype: dict
        :raises MetaWorkflowRunCreationError: If no CRAM files could be
            found on a Sample
        """
        result = {}
        for idx, sample in enumerate(self.sorted_samples):
            cram_uuids = []
            cram_files = sample.get(self.CRAM_FILES)
            if cram_files is None:
                raise MetaWorkflowRunCreationError(
                    "Tried to grab CRAM files from a Sample lacking them: %s" % sample
                )
            for cram_file in cram_files:
                cram_uuid = cram_file.get(self.UUID)
                cram_uuids.append(cram_uuid)
            result[idx] = cram_uuids
        return result

    @property
    def input_gvcfs(self):
        """gVCF file input.
        """
        return self.get_samples_processed_file_for_format(self.GVCF_FORMAT)

    @property
    def fastqs_r1(self):
        """FASTQ paired-end 1 file input.
        """
        return self.get_fastqs_for_paired_end(self.PAIRED_END_1)

    @property
    def fastqs_r2(self):
        """FASTQ paired-end 2 file input.
        """
        return self.get_fastqs_for_paired_end(self.PAIRED_END_2)

    @property
    def input_bams(self):
        """BAM file input.
        """
        return self.get_samples_processed_file_for_format(self.BAM_FORMAT)

    @property
    def rcktar_file_names(self):
        """Sorted names for created RckTar files input.
        """
        return [
            sample_name + self.RCKTAR_FILE_ENDING for sample_name in self.sample_names
        ]

    @property
    def sample_name_proband(self):
        """Proband Sample name input.
        """
        return self.sample_names[0]  # Already sorted to proband-first

    @property
    def bamsnap_titles(self):
        """Sorted BAMSnap name input.
        """
        result = []
        for sample_pedigree in self.sorted_samples_pedigree:
            sample_name = sample_pedigree.get(self.SAMPLE_NAME)
            sample_relationship = sample_pedigree.get(self.RELATIONSHIP, "")
            result.append("%s (%s)" % (sample_name, sample_relationship))
        return result

    @property
    def family_size(self):
        """Family size input.
        """
        return len(self.sample_names)
