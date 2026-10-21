from rest_framework import serializers


class RouteTripQuerySerializer(serializers.Serializer):
    """
    Validates origin and destination query parameters for route planning.
    """
    start = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=200,
        error_messages={
            "required": "parameter 'start' is required.",
            "blank": "parameter 'start' cannot be empty.",
        },
    )
    finish = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=200,
        error_messages={
            "required": "parameter 'finish' is required.",
            "blank": "parameter 'finish' cannot be empty.",
        },
    )
