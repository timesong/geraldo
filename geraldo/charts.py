from reportlab.graphics.shapes import Drawing, String

from reportlab.graphics.charts.barcharts import HorizontalBarChart as OriginalHorizBarChart
from reportlab.graphics.charts.barcharts import VerticalBarChart as OriginalVertBarChart
from reportlab.graphics.charts.barcharts import HorizontalBarChart3D as OriginalHorizBarChart3D
from reportlab.graphics.charts.barcharts import VerticalBarChart3D as OriginalVertBarChart3D
from reportlab.graphics.charts.doughnut import Doughnut as OriginalDoughnutChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart as OriginalLineChart
from reportlab.graphics.charts.piecharts import Pie as OriginalPieChart
from reportlab.graphics.charts.spider import SpiderChart as OriginalSpiderChart
from reportlab.graphics.charts.legends import LineLegend

from utils import cm, memoize, get_attr_value
from cross_reference import CrossReferenceMatrix, CROSS_COLS, CROSS_ROWS
from graphics import Graphic

DEFAULT_TITLE_HEIGHT = 1*cm

class BaseChart(Graphic):
    """Abstract chart class"""

    chart_class = None
    title = None
    colors = None
    _width = 8*cm
    _height = 7*cm
    rows_attribute = None
    cols_attribute = None
    cell_attribute = None
    action = 'first'
    data = None
    chart_style = None # Additional chart attributes
    axis_labels = None
    axis_labels_angle = None
    legend_labels = False
    values_labels = ' %s '
    replace_none_by_zero = True
    summarize_by = None # Can be None, CROSS_ROWS or CROSS_COLS

    def __init__(self, **kwargs):
        # Set instance attributes
        for k,v in kwargs.items():
            if k == 'style':
                setattr(self, 'chart_style', v)
            else:
                setattr(self, k, v)

        # Prepare the title
        if self.title:
            self.title = isinstance(self.title, dict) and self.title or {'text': self.title}
            self.title.setdefault('fontSize', 14)
            self.title.setdefault('textAnchor', 'middle')
            self.title.setdefault('height', DEFAULT_TITLE_HEIGHT)

        # Prepare the colors
        if self.colors == False:
            self.legend_labels = None
        elif not self.colors:
            self.colors = self.get_available_colors()

        # Prepare chart additional kwargs
        self.chart_style = self.chart_style or {}

    def clone(self):
        new = super(BaseChart, self).clone()

        new.chart_class = self.chart_class
        new.title = self.title
        new.colors = self.colors
        new.rows_attribute = self.rows_attribute
        new.cols_attribute = self.cols_attribute
        new.cell_attribute = self.cell_attribute
        new.action = self.action
        new.data = self.data
        new.chart_style = self.chart_style
        new.axis_labels = self.axis_labels
        new.axis_labels_angle = self.axis_labels_angle
        new.legend_labels = self.legend_labels
        new.values_labels = self.values_labels
        new.replace_none_by_zero = self.replace_none_by_zero
        new.summarize_by = self.summarize_by

        return new

    # DRAWING METHODS

    @memoize
    def get_available_colors(self):
        """Returns a list of available colors"""
        import random
        from reportlab.lib.colors import getAllNamedColors

        # Get reportlab available colors
        colors = getAllNamedColors()

        # Remove bad colors
        colors.pop('white', None)
        colors.pop('black', None)

        # Returns only the colors values (without their names)
        colors = colors.values()
        
        # Shuffle colors list
        random.shuffle(colors)

        return colors

    def get_drawing(self, chart):
        """Create and returns the drawing, to be generated"""

        drawing = Drawing(self.width, self.height)

        # Make the title
        title = self.make_title(drawing)

        # Make the legend
        legend = self.make_legend(drawing, chart)

        # Setting chart dimensions
        chart.height = self.height
        chart.width = self.width

        if title:
            chart.height -= self.title.get('height', DEFAULT_TITLE_HEIGHT)
            self.top += self.title.get('height', DEFAULT_TITLE_HEIGHT)

        if legend:
            chart.width = legend.getBounds()[0]

        # Setting additional chart attributes
        self.set_chart_style(chart)

        # Adds the chart to drawing to return
        drawing.add(chart)

        # Resizes to make sure everything is fitting
        drawing = drawing.resized()

        return drawing

    def make_legend(self, drawing, chart):
        if not self.legend_labels:
            return

        # Get legend labels
        labels = self.get_legend_labels()

        # Legend object
        legend = LineLegend()
        #legend.fontName = 'Times-Roman'
        #legend.fontSize = 12

        legend.colorNamePairs = zip(self.colors[:len(labels)], labels)
        legend.columnMaximum = len(legend.colorNamePairs)
        legend.deltay = 5
        legend.alignment = 'right'
        legend.x = drawing.width
        legend.y = drawing.height - (self.title and self.title.get('height', DEFAULT_TITLE_HEIGHT) or 0)

        drawing.add(legend)

        return legend

    def get_legend_labels(self):
        # Use same axis if is summarizing
        if self.summarize_by:
            return self.get_axis_labels()

        # Base labels
        if isinstance(self.legend_labels, (tuple,list)):
            labels = self.legend_labels
        else:
            labels = self.get_cross_data().rows()

        # Calculated labels
        if callable(self.legend_labels):
            labels = [self.legend_labels(self, label, num) for num, label in enumerate(labels)]
        elif isinstance(self.legend_labels, basestring):
            labels = [self.get_cross_data().first(self.legend_labels, col=label) for label in labels]

        return map(unicode, labels)

    def get_axis_labels(self):
        # Base labels
        if isinstance(self.axis_labels, (tuple,list)):
            labels = self.axis_labels
        elif self.summarize_by == CROSS_ROWS:
            labels = self.get_cross_data().rows()
        else:
            labels = self.get_cross_data().cols()

        # Calculated labels
        if callable(self.axis_labels):
            labels = [self.axis_labels(self, label, num) for num, label in enumerate(labels)]
        elif isinstance(self.axis_labels, basestring):
            if self.summarize_by == CROSS_ROWS:
                labels = [self.get_cross_data().first(self.axis_labels, row=label) for label in labels]
            else:
                labels = [self.get_cross_data().first(self.axis_labels, col=label) for label in labels]

        return map(unicode, labels)

    def make_title(self, drawing):
        if not self.title:
            return

        # Make the dict with kwargs
        kwargs = self.title.copy()
        kwargs.setdefault('x', drawing.width / 2)
        kwargs.setdefault('y', drawing.height)

        # Make the string
        title = String(**kwargs)

        drawing.add(title)

        return title

    # CHART METHODS

    def get_cross_data(self, data=None):
        if not getattr(self, '_cross_data', None):
            data = data or self.data

            # Transforms data to cross-reference matrix
            if isinstance(data, basestring):
                data = get_attr_value(self.instance, data)

            if not isinstance(data, CrossReferenceMatrix):
                if self.rows_attribute: # and self.cols_attribute:
                    data = CrossReferenceMatrix(
                            data,
                            self.rows_attribute,
                            self.cols_attribute,
                            decimal_as_float=True,
                            )

            self._cross_data = data

        return self._cross_data

    def get_data(self):
        data = self.data

        # Returns nothing data is empty
        if not data:
            data = self.report.queryset # TODO: Change to support current objects
                                        # list (for subreports and groups)

        # Transforms data to cross-reference matrix
        data = self.get_cross_data(data)

        # Summarize data or get its matrix (after it is a Cross-Reference Matrix)
        if self.summarize_by == CROSS_ROWS:
            data = data.summarize_rows(self.cell_attribute, self.action)
        elif self.summarize_by == CROSS_COLS:
            data = data.summarize_cols(self.cell_attribute, self.action)
        else:
            data = data.matrix(self.cell_attribute, self.action)

        def none_to_zero(value):
            if value is None:
                value = 0
            elif isinstance(value, (list, tuple)):
                value = [cell or 0 for cell in value]

            return value

        # Replace None to Zero
        if self.replace_none_by_zero:
            data = map(none_to_zero,  data)

        return data

    def set_chart_attributes(self, chart):
        # Cols (Y) labels - Y axis
        if self.axis_labels:
            chart.categoryAxis.categoryNames = self.get_axis_labels()

            if self.axis_labels_angle is not None:
                chart.categoryAxis.labels.angle = self.axis_labels_angle
                chart.categoryAxis.labels.boxAnchor = 'ne'

    def set_chart_style(self, chart):
        # Setting additional chart attributes
        if self.chart_style:
            for k,v in self.chart_style.items():
                setattr(chart, k, v)

    def create_chart(self):
        chart = self.chart_class()

        return chart

    def render(self):
        # Make data matrix
        data = self.get_data()

        if not data:
            return

        # Creates the chart instance
        chart = self.create_chart()
        chart.data = data

        # Sets additional attributes
        self.set_chart_attributes(chart)

        return self.get_drawing(chart)

class BaseMatrixChart(BaseChart):
    """Abstract chart class to support matrix charts"""

    def get_data(self):
        data = super(BaseMatrixChart, self).get_data()

        if data and self.summarize_by:
            data = [data]
        
        return data

class LineChart(BaseMatrixChart):
    chart_class = OriginalLineChart

    def set_chart_attributes(self, chart):
        super(LineChart, self).set_chart_attributes(chart)

        # Cells labels
        if self.values_labels:
            self.chart_style.setdefault('lineLabelFormat', self.values_labels)
        else:
            self.chart_style.pop('lineLabelFormat', None)

        # Set the line colors
        if self.colors:
            for num, color in enumerate(self.colors):
                try:
                    chart.lines[num].strokeColor = color
                except IndexError:
                    break

class BarChart(BaseMatrixChart):
    chart_class = None
    horizontal = False # If is not horizontal, is because it is vertical (default)
    is3d = False

    def __init__(self, *args, **kwargs):
        super(BarChart, self).__init__(*args, **kwargs)

        # Chart class varies depending on attributes
        if not self.chart_class:
            if self.horizontal and self.is3d:
                self.chart_class = OriginalHorizBarChart3D
            elif self.horizontal:
                self.chart_class = OriginalHorizBarChart
            elif self.is3d:
                self.chart_class = OriginalVertBarChart3D
            else:
                self.chart_class = OriginalVertBarChart

    def clone(self):
        new = super(BarChart, self).clone()

        new.horizontal = self.horizontal
        new.is3d = self.is3d

        return new

    def set_chart_attributes(self, chart):
        super(BarChart, self).set_chart_attributes(chart)

        # Cells labels
        if self.values_labels:
            self.chart_style.setdefault('barLabelFormat', self.values_labels)

            # Label orientation
            if self.horizontal:
                chart.barLabels.boxAnchor = 'w'
            else:
                chart.barLabels.boxAnchor = 's'
        else:
            self.chart_style.pop('barLabelFormat', None)

        # Set bar strokes
        chart.bars.strokeWidth = 0

        # Set the bar colors
        if self.colors:
            for num, color in enumerate(self.colors):
                try:
                    chart.bars[num].fillColor = color
                except IndexError:
                    break

class HorizontalBarChart(BarChart):
    horizontal = True

class SpiderChart(BaseMatrixChart):
    chart_class = OriginalSpiderChart

    def set_chart_attributes(self, chart):
        # Chart labels
        chart.labels = self.get_axis_labels()

        # Set the strands colors
        if self.colors:
            for num, color in enumerate(self.colors):
                try:
                    chart.strands[num].fillColor = color
                except IndexError:
                    break

class PieChart(BaseChart):
    chart_class = OriginalPieChart
    slice_popout = None

    def __init__(self, **kwargs):
        super(PieChart, self).__init__(**kwargs)

        # Force default value for summarize
        if not self.summarize_by:
            self.summarize_by = CROSS_ROWS

    def set_chart_attributes(self, chart):
        chart.labels = self.get_axis_labels()

        # Sets the slice colors
        if self.colors:
            for num, color in enumerate(self.colors):
                try:
                    chart.slices[num].fillColor = color
                except IndexError:
                    break

        # Sets the slice to popout
        pos = -1
        if self.slice_popout == True:
            data = self.get_data()
            pos = data.index(max(data))
        elif isinstance(self.slice_popout, int):
            pos = self.slice_popout
        elif callable(self.slice_popout):
            pos = self.slice_popout(self, chart)

        if pos >= 0:
            chart.slices[pos].popout = 20

    def clone(self):
        new = super(PieChart, self).clone()
        new.slice_popout = self.slice_popout
        return new

class DoughnutChart(PieChart):
    chart_class = OriginalDoughnutChart

