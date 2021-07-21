#!/usr/bin/env python3

################################################
#
#
#
################################################

################################################
#   Libraries
################################################
import sys, os

# dcicutils
from dcicutils import ff_utils
from dcicutils.s3_utils import s3Utils

################################################
#   FFWfrUtils
################################################
class FFWfrUtils(object):
    def __init__(self, env):
        """
                env : e.g. 'fourfront-cgap', 'fourfront-cgap-wolf'
        """
        self.env = env

        # Cache for metadata
        self._metadata = dict()
        # Cache for access key
        self._ff_key = None

    def wfr_run_uuid(self, job_id):
        """
            this is the function to be used by Magma.
        """
        wfr_meta = self.wfr_metadata(job_id)
        if not wfr_meta:
            return None
        return wfr_meta['uuid']

    def wfr_run_status(self, job_id):
        """
            This is the function to be used by Magma.
            Returns the run status of the wfr associated with the job id.
            If wfr associated with job id is not found, we consider it failed.
        """
        wfr_meta = self.wfr_metadata(job_id)
        if not wfr_meta:
            return 'failed'
        else:
            return wfr_meta['run_status']

    def get_minimal_processed_output(self, job_id):
        """
            this is the function to be used by Magma.
            returns a list of {'argument_name': <arg_name>, 'file': <uuid>}
            for all processed file output.
            If no output, returns None.
        """
        wfr_output = self.wfr_output(job_id)
        return self.filter_wfr_output_minimal_processed(wfr_output)

    def wfr_output(self, job_id):
        """
            return the raw output from the wfr metadata.
            returns None if wfr metadata associated with the job is not found or
            does not have associated output files.
        """
        if self.wfr_metadata(job_id):
            return self.wfr_metadata(job_id).get('output_files', None)
        else:
            return None

    def wfr_metadata(self, job_id):
        """
            get portal WorkflowRun metadata from job id
            returns None if a workflow run associated with job id cannot be found.
        """
        # Use cache
        if job_id in self._metadata:
            return self._metadata[job_id]
        # Search by job id
        query='/search/?type=WorkflowRun&awsem_job_id=%s' % job_id
        try:
            search_res = ff_utils.search_metadata(query, key=self.ff_key)
        except Exception as e:
            raise FdnConnectionException(e)
        if search_res:
            self._metadata[job_id] = search_res[0]
            return self._metadata[job_id]
        else:
            # find it from dynamoDB
            job_info = Job.info(job_id)
            if not job_info:
                return None
            wfr_uuid = job_info.get('WorkflowRun uuid', '')
            if not wfr_uuid:
                return None
            self._metadata[job_id] = ff_utils.get_metadata(wfr_uuid, key=self.ff_key)
            return self._metadata[job_id]

    @property
    def ff_key(self):
        """
            get access key for the portal
        """
        # Use cache
        if not self._ff_key:
            # Use tibanna key for now
            self._ff_key = s3Utils(env=self.env).get_access_keys('access_key_tibanna')
        return self._ff_key

    @staticmethod
    def filter_wfr_output_minimal_processed(wfr_output):
        """
            return a list of {'argument_name': <arg_name>, 'file': <uuid>}
            for all processed file output
        """
        if wfr_output:
            return [{'argument_name': opf['workflow_argument_name'],
                     'file': opf['value']['uuid']} \
                        for opf in wfr_output \
                            if opf['type'] == 'Output processed file']
        else:
            return None

#end class


class FdnConnectionException(Exception):
    pass

#end class
