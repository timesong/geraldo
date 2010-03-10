import datetime, types, decimal

try: 
    set 
except NameError: 
    from sets import Set as set     # Python 2.3 fallback 

from reportlab.lib.units import cm
from reportlab.lib.colors import black

from base import BAND_WIDTH, BAND_HEIGHT, Element
from utils import get_attr_value, SYSTEM_FIELD_CHOICES, FIELD_ACTION_VALUE, FIELD_ACTION_COUNT,\
        FIELD_ACTION_AVG, FIELD_ACTION_MIN, FIELD_ACTION_MAX, FIELD_ACTION_SUM,\
        FIELD_ACTION_DISTINCT_COUNT
from exceptions import AttributeNotFound

class Widget(Element):
    """A widget is a value representation on the report"""
    _height = 0 #0.5*cm
    _width = 5*cm
    style = {}
    truncate_overflow = False
    
    get_value = None # A lambda function to get customized values

    instance = None
    report = None
    generator = None
    band = None

    def __init__(self, **kwargs):
        """This initializer is prepared to set arguments informed as attribute
        values."""
        for k,v in kwargs.items():
            setattr(self, k, v)

    def clone(self):
        new = super(Widget, self).clone()
        new.style = self.style
        new.truncate_overflow = self.truncate_overflow

        new.get_value = self.get_value

        new.instance = self.instance
        new.report = self.report
        new.generator = self.generator
        new.band = self.band

        return new

class Label(Widget):
    """A label is just a simple text.
    
    'get_value' lambda must have 'text' argument."""
    _text = ''

    _repr_for_cache_attrs = ('text','left','top','height','width','style','visible')

    def _get_text(self):
        if self.get_value:
            return self.get_value(self._text)

        return self._text

    def _set_text(self, value):
        self._text = value

    text = property(_get_text, _set_text)

    def clone(self):
        new = super(Label, self).clone()

        if not callable(self._text):
            new._text = self._text

        return new

class ObjectValue(Label):
    """This shows the value from a method, field or property from objects got
    from the queryset.
    
    You can inform an action to show the object value or an aggregation
    function on it.
    
    You can also use 'display_format' attribute to set a friendly string
    formating, with a mask or additional text.
    
    'get_value' and 'get_text' lambda attributes must have 'instance' argument.
    
    Set 'stores_text_in_cache' to False if you want this widget get its value
    and text on render and generate moments."""

    attribute_name = None
    action = FIELD_ACTION_VALUE
    display_format = '%s'
    objects = None
    get_text = None # A lambda function to get customized display values
    stores_text_in_cache = True
    _cached_text = None

    def get_object_value(self, instance=None):
        """Return the attribute value for just an object"""
        instance = instance or self.instance

        if self.get_value and instance:
            try:
                return self.get_value(self, instance)
            except TypeError:
                return self.get_value(instance)

        value = get_attr_value(instance, self.attribute_name)

        # For method attributes --- FIXME: check what does this code here, because
        #                           get_attr_value has a code to do that, using
        #                           callable() checking
        if type(value) == types.MethodType:
            value = value()

        return value

    def get_queryset_values(self):
        """Uses the method 'get_object_value' to get the attribute value from
        all objects in the objects list, as a list"""

        objects = self.generator.get_current_queryset()
        return map(self.get_object_value, objects)

    def _clean_empty_values(self, values):
        def _clean(val):
            if not val:
                return 0
            elif isinstance(val, decimal.Decimal):
                return float(val)
            
            return val

        return map(_clean, values)

    def action_value(self):
        return self.get_object_value()

    def action_count(self):
        # Returns the total count of objects with valid values on informed attribute
        values = self.get_queryset_values()
        return len(filter(lambda v: v is not None, values))

    def action_avg(self):
        values = self.get_queryset_values()

        # Clear empty values
        values = self._clean_empty_values(values)

        return sum(values) / len(values)

    def action_min(self):
        values = self.get_queryset_values()
        return min(values)

    def action_max(self):
        values = self.get_queryset_values()
        return max(values)

    def action_sum(self):
        values = self.get_queryset_values()

        # Clear empty values
        values = self._clean_empty_values(values)

        return sum(values)

    def action_distinct_count(self):
        values = filter(lambda v: v is not None, self.get_queryset_values())
        return len(set(values))

    def _text(self):
        if not self.stores_text_in_cache or self._cached_text is None:
            try: # Before all, tries to get the value using parent object
                value = self.band.get_object_value(obj=self)
            except AttributeNotFound:
                value = getattr(self, 'action_'+self.action)()

            if self.get_text:
                self._cached_text = unicode(self.get_text(self.instance, value))
            else:
                self._cached_text = unicode(value)
            
        return self.display_format % self._cached_text
    text = property(lambda self: self._text())

    def clone(self):
        new = super(ObjectValue, self).clone()
        new.attribute_name = self.attribute_name
        new.action = self.action
        new.display_format = self.display_format
        new.objects = self.objects
        new.stores_text_in_cache = self.stores_text_in_cache

        return new

class SystemField(Label):
    """This shows system informations, like the report title, current date/time,
    page number, pages count, etc.
    
    'get_value' lambda must have 'expression' and 'fields' argument."""
    expression = '%(report_title)s'

    fields = {
            'report_title': None,
            'page_number': None,
            'first_page_number': None,
            'last_page_number': None,
            'page_count': None,
            'current_datetime': None,
            'report_author': None,
        }

    def __init__(self, **kwargs):
        super(SystemField, self).__init__(**kwargs)

        # This is the safe way to use the predefined fields dictionary
        self.fields = SystemField.fields.copy()

        self.fields['current_datetime'] = datetime.datetime.now()

    def text(self):
        page_number = (self.fields.get('page_number') or self.generator._current_page_number) + self.generator.first_page_number - 1
        page_count = self.fields.get('page_count') or self.generator.get_page_count()

        fields = {
            'report_title': self.fields.get('report_title') or self.report.title,
            'page_number': page_number,
            'first_page_number': self.generator.first_page_number,
            'last_page_number': page_count + self.generator.first_page_number - 1,
            'page_count': page_count,
            'current_datetime': self.fields.get('current_datetime') or datetime.datetime.now(),
            'report_author': self.fields.get('report_author') or self.report.author,
        }
        
        if self.get_value:
            return self.get_value(self.expression, fields)

        return self.expression%SystemFieldDict(self, fields)
    text = property(text)

    def clone(self):
        new = super(SystemField, self).clone()
        new.expression = self.expression
        new.fields = self.fields

        return new

class SystemFieldDict(dict):
    widget = None
    fields = None

    def __init__(self, widget, fields):
        self.widget = widget
        self.fields = fields or {}

        super(SystemFieldDict, self).__init__(**fields)

    def __getitem__(self, key):
        if key.startswith('now:'):
            return self.widget.report.format_date(
                    self.fields.get('current_datetime', datetime.datetime.now()),
                    key[4:]
                    )

        elif key.startswith('var:'):
            return self.widget.report.get_variable_value(name=key[4:], system_fields=self)

        return self.fields[key]

class PageBreak(Widget):
    pass