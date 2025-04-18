from django.conf import settings
from django.db.models import Prefetch
from django_elasticsearch_dsl import Index, fields
from opaque_keys.edx.keys import CourseKey
from taxonomy.choices import ProductTypes
from taxonomy.utils import get_whitelisted_serialized_skills

from course_discovery.apps.api.utils import get_retired_course_type_ids
from course_discovery.apps.course_metadata.models import Course, CourseRun
from course_discovery.apps.course_metadata.utils import get_product_skill_names

from .analyzers import case_insensitive_keyword
from .common import BaseCourseDocument, filter_visible_runs

__all__ = ('CourseDocument',)

COURSE_INDEX_NAME = settings.ELASTICSEARCH_INDEX_NAMES[__name__]
COURSE_INDEX = Index(COURSE_INDEX_NAME)
COURSE_INDEX.settings(
    number_of_shards=1,
    number_of_replicas=1,
    blocks={'read_only_allow_delete': None},
)


@COURSE_INDEX.doc_type
class CourseDocument(BaseCourseDocument):
    """
    Course Elasticsearch document.
    """

    availability = fields.TextField(
        fields={'raw': fields.KeywordField(), 'lower': fields.TextField(analyzer=case_insensitive_keyword)},
        multi=True
    )
    card_image_url = fields.TextField()
    course_runs = fields.KeywordField(multi=True)
    expected_learning_items = fields.KeywordField(multi=True)
    end = fields.DateField(multi=True)
    course_ends = fields.TextField(
        fields={'raw': fields.KeywordField(), 'lower': fields.TextField(analyzer=case_insensitive_keyword)}
    )
    end_date = fields.DateField()
    enrollment_start = fields.DateField(multi=True)
    enrollment_end = fields.DateField(multi=True)
    first_enrollable_paid_seat_price = fields.IntegerField()
    languages = fields.KeywordField(multi=True)
    modified = fields.DateField()
    prerequisites = fields.KeywordField(multi=True)
    skill_names = fields.KeywordField(multi=True)
    skills = fields.NestedField(properties={
        'name': fields.TextField(),
        'description': fields.TextField(),
    })
    status = fields.KeywordField(multi=True)
    start = fields.DateField(multi=True)
    course_type = fields.KeywordField(multi=True)
    enterprise_subscription_inclusion = fields.BooleanField()
    course_length = fields.KeywordField()
    external_course_marketing_type = fields.KeywordField(multi=True)
    product_source = fields.KeywordField(multi=True)

    def prepare_aggregation_key(self, obj):
        return 'course:{}'.format(obj.key)

    def prepare_aggregation_uuid(self, obj):
        return 'course:{}'.format(obj.uuid)

    def prepare_availability(self, obj):
        return [str(course_run.availability) for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_course_runs(self, obj):
        return [course_run.key for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_expected_learning_items(self, obj):
        return [item.value for item in obj.expected_learning_items.all()]

    def prepare_languages(self, obj):
        return list(
            {
                self._prepare_language(course_run.language)
                for course_run in filter_visible_runs(obj.course_runs)
                if course_run.language
            }
        )

    def prepare_end(self, obj):
        return [course_run.end for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_end_date(self, obj):
        return obj.end_date

    def prepare_course_ends(self, obj):
        return str(obj.course_ends)

    def prepare_enrollment_start(self, obj):
        return [course_run.enrollment_start for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_enrollment_end(self, obj):
        return [course_run.enrollment_end for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_org(self, obj):
        course_run = filter_visible_runs(obj.course_runs).first()
        if course_run:
            return CourseKey.from_string(course_run.key).org
        return None

    def prepare_seat_types(self, obj):
        seat_types = [seat.slug for run in filter_visible_runs(obj.course_runs) for seat in run.seat_types]
        return list(set(seat_types))

    def prepare_skill_names(self, obj):
        return get_product_skill_names(obj.key, ProductTypes.Course)

    def prepare_skills(self, obj):
        return get_whitelisted_serialized_skills(obj.key, product_type=ProductTypes.Course)

    def prepare_status(self, obj):
        return [course_run.status for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_start(self, obj):
        return [course_run.start for course_run in filter_visible_runs(obj.course_runs)]

    def prepare_prerequisites(self, obj):
        return [prerequisite.name for prerequisite in obj.prerequisites.all()]

    def get_queryset(self, excluded_restriction_types=None):
        if excluded_restriction_types is None:
            excluded_restriction_types = []
        retired_type_ids = get_retired_course_type_ids()

        return super().get_queryset().exclude(type_id__in=retired_type_ids).prefetch_related(
            Prefetch('course_runs', queryset=CourseRun.objects.exclude(
                restricted_run__restriction_type__in=excluded_restriction_types
            ).prefetch_related(
                'seats__type', 'type', 'language', 'restricted_run',
            ))
        ).select_related('partner')

    def prepare_course_type(self, obj):
        return obj.type.slug

    def prepare_course_length(self, obj):
        return obj.course_length

    def prepare_enterprise_subscription_inclusion(self, obj):
        return obj.enterprise_subscription_inclusion

    def prepare_external_course_marketing_type(self, obj):
        return obj.additional_metadata.external_course_marketing_type if obj.additional_metadata else None

    def prepare_product_source(self, obj):
        return obj.product_source.slug if obj.product_source else None

    class Django:
        """
        Django Elasticsearch DSL ORM Meta.
        """

        model = Course

    class Meta:
        """
        Meta options.
        """

        parallel_indexing = True
        queryset_pagination = settings.ELASTICSEARCH_DSL_QUERYSET_PAGINATION
