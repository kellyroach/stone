"""
Defines all of Babel's primitive types in Python. Also provides the high-level
classes that should be extended when defining composite data types.

The data types defined here should not be specific to an RPC or serialization
format.

This module should be dropped into a project that requires the use of Babel. In
the future, this could be imported from a pre-installed Python package, rather
than being added to a project.
"""

from abc import ABCMeta, abstractmethod
import datetime
import numbers
import re
import six

class ValidationError(Exception):
    pass

def generic_type_name(v):
    """Return a descriptive type name that isn't Python specific. For example,
    an int value will return 'integer' rather than 'int'."""
    if isinstance(v, numbers.Integral):
        # Must come before real numbers check since integrals are floats too
        return 'integer'
    elif isinstance(v, numbers.Real):
        return 'float'
    elif isinstance(v, (tuple, list)):
        return 'list'
    elif isinstance(v, six.string_types):
        return 'string'
    else:
        return type(v).__name__

class DataType(object):
    """All primitive and composite data types should extend this."""
    __metaclass__ = ABCMeta

    @abstractmethod
    def validate(self, val):
        """Validates that val is of this data type.

        Returns: None if validation succeeds.
        Raises: ValidationError
        """
        pass

class PrimitiveType(DataType):
    """A basic type that is defined by Babel."""
    pass

class Boolean(PrimitiveType):
    def validate(self, val):
        if not isinstance(val, bool):
            raise ValueError('%r is not a valid boolean' % val)

class _Integer(PrimitiveType):
    """
    Do not use this class directly. Extend it and specify a 'minimum' and
    'maximum' value as class variables for the more restrictive integer range.
    """
    minimum = None
    maximum = None

    def __init__(self, min_value=None, max_value=None):
        """
        A more restrictive minimum or maximum value can be specified than the
        range inherent to the defined type.
        """
        if min_value is not None:
            assert isinstance(max_value, numbers.Integral), (
                'min_value must be an integral number'
            )
            if min_value < self.minimum:
                raise ValueError('min_value cannot be less than the minimum '
                                 'value for this type (%d < %d)'
                                 % (min_value, self.minimum))
            self.minimum = min_value
        if max_value is not None:
            assert isinstance(max_value, numbers.Integral), (
                'max_value must be an integral number'
            )
            if max_value > self.maximum:
                raise ValueError('max_value cannot be greater than the maximum '
                                 'value for this type (%d < %d)'
                                 % (max_value, self.maximum))
            self.maximum = max_value

    def validate(self, val):
        if not isinstance(val, numbers.Integral):
            raise ValidationError('%r is of type %r and is not a valid integer type'
                                  % (val, type(val)))
        elif not (self.minimum <= val <= self.maximum):
            raise ValidationError('%d is not within range [%d, %d]'
                                  % (val, self.minimum, self.maximum))

    def __repr__(self):
        return '%s()' % self.__class__.__name__

class Int32(_Integer):
    minimum = -2**31
    maximum = 2**31 - 1

class UInt32(_Integer):
    minimum = 0
    maximum = 2**32 - 1

class Int64(_Integer):
    minimum = -2**63
    maximum = 2**63 - 1

class UInt64(_Integer):
    minimum = 0
    maximum = 2**64 - 1

class String(PrimitiveType):
    """Represents a unicode string."""
    def __init__(self, min_length=None, max_length=None, pattern=None):
        if min_length is not None:
            assert isinstance(min_length, numbers.Integral), (
                'min_length must be an integral number'
            )
            assert min_length >= 0, 'min_length must be >= 0'
        if max_length is not None:
            assert isinstance(max_length, numbers.Integral), (
                'max_length must be an integral number'
            )
            assert max_length > 0, 'max_length must be > 0'
        if min_length and max_length:
            assert max_length >= min_length, 'max_length must be >= min_length'
        if pattern is not None:
            assert isinstance(pattern, six.string_types), (
                'pattern must be a string'
            )

        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.pattern_re = None

        if pattern:
            try:
                self.pattern_re = re.compile(pattern)
            except re.error as e:
                raise ValueError('Regex {!r} failed: {}'.format(pattern, e.args[0]))

    def validate(self, val):
        """
        A unicode string of the correct length will pass validation. In PY2,
        we enforce that a str type must be valid utf-8.
        """
        if not isinstance(val, six.string_types):
            raise ValidationError("'%s' expected to be a string, got %s"
                                  % (val, generic_type_name(val)))
        elif self.max_length is not None and len(val) > self.max_length:
            raise ValidationError("'%s' must be at most %d characters, got %d"
                                  % (val, self.max_length, len(val)))
        elif self.min_length is not None and len(val) < self.min_length:
            raise ValidationError("'%s' must be at least %d characters, got %d"
                                  % (val, self.min_length, len(val)))

        if not six.PY3 and isinstance(val, str):
            try:
                val.decode('utf-8')
            except UnicodeDecodeError:
                raise ValidationError("'%s' was not valid utf-8")

        if self.pattern and not self.pattern_re.match(val):
            raise ValidationError("'%s' did not match pattern '%s'"
                                  % (val, self.pattern))

class Binary(PrimitiveType):
    def __init__(self, min_length=None, max_length=None):
        if min_length is not None:
            assert isinstance(min_length, numbers.Integral), (
                'min_length must be an integral number'
            )
            assert min_length >= 0, 'min_length must be >= 0'
        if max_length is not None:
            assert isinstance(max_length, numbers.Integral), (
                'max_length must be an integral number'
            )
            assert max_length > 0, 'max_length must be > 0'
        if min_length is not None and max_length is not None:
            assert max_length >= min_length, 'max_length must be >= min_length'

        self.min_length = min_length
        self.max_length = max_length

    def validate(self, val):
        if not isinstance(val, bytes):
            # TODO(kelkabany): Add support for buffer and file objects.
            raise ValidationError("Expected binary type, got %s"
                                  % generic_type_name(val))
        elif self.max_length is not None and len(val) > self.max_length:
            raise ValidationError("'%s' must have at most %d bytes, got %d"
                                  % (val, self.max_length))
        elif self.min_length is not None and len(val) < self.min_length:
            raise ValidationError("'%s' has fewer than %d bytes"
                                  % (val, self.min_length))

class Timestamp(PrimitiveType):
    """Note that while a format is specified, it isn't used in validation
    since a native Python datetime object is preferred. The format, however,
    can and should be used by serializers."""

    def __init__(self, format):
        assert isinstance(format, str), (
            'format must be a string'
        )
        self.format = format

    def validate(self, val):
        if not isinstance(val, datetime.datetime):
            raise ValueError('%r is of type %r and is not a valid timestamp'
                             % (val, type(val).__name__))

class List(PrimitiveType):
    """Assumes list contents are homogeneous with respect to types."""

    def __init__(self, data_type, min_items=None, max_items=None):
        self.data_type = data_type
        if min_items is not None:
            assert isinstance(min_items, numbers.Integral), (
                'min_items must be an integral number'
            )
            assert min_items >= 0, 'min_items must be >= 0'
        if max_items is not None:
            assert isinstance(max_items, numbers.Integral), (
                'max_items must be an integral number'
            )
            assert max_items > 0, 'max_items must be > 0'
        if min_items is not None and max_items is not None:
            assert max_items >= min_items, 'max_items must be >= min_items'

        self.min_items = min_items
        self.max_items = max_items

    def validate(self, val):
        if not isinstance(val, (tuple, list)):
            raise ValidationError('%r is not a valid list' % val)
        elif self.max_items is not None and len(val) > self.max_items:
            raise ValidationError('%r has more than %s items'
                                  % (val, self.max_items))
        elif self.min_items is not None and len(val) < self.min_items:
            raise ValidationError('%r has fewer than %s items'
                                  % (val, self.min_items))
        for item in val:
            self.data_type.validate(item)

class CompositeType(DataType):
    def __init__(self, data_type):
        self.data_type = data_type
    def validate_type_only(self, val):
        if type(val) is not self.data_type:
            raise ValidationError('Expected type %s, got %s'
                % (self.data_type.__name__, generic_type_name(val)))

class Struct(CompositeType):
    def validate(self, val):
        """
        For a val to pass validation, it must have a _fields_ class variable
        with the following structure:

            _fields_ = [(field_name, data_type), ...]

            field_name: Name of the field (str).
            data_type: DataType object.
        """
        self.validate_type_only(val)
        for field_name, _ in self.data_type._fields_:
            # Any absent field that's required will raise a KeyError
            try:
                getattr(val, field_name)
            except AttributeError as e:
                raise ValidationError(e.args[0])

class Union(CompositeType):
    def validate(self, val):
        """
        For a val to pass validation, it must have a _fields_ class variable
        with the following structure:

            _fields_ = {field_name: data_type, ...}

            field_name: Name of the tag (str).
            data_type: DataType object. None if it's a symbol field.
        """
        self.validate_type_only(val)
        if val._tag is None:
            raise ValidationError('No tag set')

class Any(DataType):
    """A special type that accepts any value."""
    def validate(self, val):
        pass

class Symbol(DataType):
    """A special type that doesn't have a corresponding value."""
    def validate(self, val):
        raise AssertionError('No value validates as a symbol.')