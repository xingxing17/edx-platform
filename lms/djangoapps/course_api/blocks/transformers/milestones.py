"""
Milestones Transformer
"""

from django.conf import settings

from edx_proctoring.api import get_attempt_status_summary
from edx_proctoring.models import ProctoredExamStudentAttemptStatus
from openedx.core.lib.block_structure.transformer import BlockStructureTransformer, FilteringTransformerMixin
from util import milestones_helpers


class MilestonesTransformer(FilteringTransformerMixin, BlockStructureTransformer):
    """
    Exclude proctored exams unless the user is not a verified student or has
    declined taking the exam. Also exclude timed exams or content with
    outstanding prerequisite milestones.
    """
    VERSION = 1

    @classmethod
    def name(cls):
        return "milestones"

    @classmethod
    def collect(cls, block_structure):
        """
        Computes any information for each XBlock that's necessary to execute
        this transformer's transform method.

        Arguments:
            block_structure (BlockStructureCollectedData)
        """
        block_structure.request_xblock_fields('is_proctored_enabled')
        block_structure.request_xblock_fields('is_practice_exam')
        block_structure.request_xblock_fields('is_timed_exam')

    def transform_block_filters(self, usage_info, block_structure):
        if usage_info.has_staff_access:
            return [block_structure.create_universal_filter()]

        def user_gated_from_block(block_key):
            """
            Checks whether the user is gated from accessing this block, first via exam proctoring, then via timed exams,
            then via a general milestones check.
            """
            return (
                settings.FEATURES.get('ENABLE_SPECIAL_EXAMS', False) and (
                    self.is_proctored_exam(block_key, usage_info, block_structure) or
                    self.is_timed_exam(block_key, block_structure)
                )
            ) or self.has_pending_milestones_for_user(block_key, usage_info)

        return [block_structure.create_removal_filter(user_gated_from_block)]

    @staticmethod
    def is_proctored_exam(block_key, usage_info, block_structure):
        """
        Test whether the block is a proctored or practice proctored exam for the user in
        question.
        """
        if (
                block_key.block_type == 'sequential' and (
                    block_structure.get_xblock_field(block_key, 'is_proctored_enabled') or
                    block_structure.get_xblock_field(block_key, 'is_practice_exam')
                )
        ):
            # This section is an exam.  It should be excluded unless the
            # user is not a verified student or has declined taking the exam.
            user_exam_summary = get_attempt_status_summary(
                usage_info.user.id,
                unicode(block_key.course_key),
                unicode(block_key),
            )
            return user_exam_summary and (
                user_exam_summary.get('status', None) != ProctoredExamStudentAttemptStatus.declined
            )
        else:
            return False

    @staticmethod
    def is_timed_exam(block_key, block_structure):
        """
        Test whether the block is a timed exam for the user in
        question. Timed exams are always excluded from student view for now.
        """
        return block_key.block_type == 'sequential' and block_structure.get_xblock_field(block_key, 'is_timed_exam')

    @staticmethod
    def has_pending_milestones_for_user(block_key, usage_info):
        """
        Test whether the current user has any unfulfilled milestones preventing
        them from accessing this block.
        """
        return bool(milestones_helpers.get_course_content_milestones(
            unicode(block_key.course_key),
            unicode(block_key),
            'requires',
            usage_info.user.id
        ))
