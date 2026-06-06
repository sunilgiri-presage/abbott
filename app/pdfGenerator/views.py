from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes

# from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

from rest_framework import status
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate,Paragraph,Spacer,PageBreak,Frame,Flowable,)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib import colors
from rest_framework import status
from rest_framework.parsers import JSONParser
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Frame,KeepTogether,Flowable,BaseDocTemplate,TableStyle,Table,Image
import pytz
from langdetect import detect
import re

timezone_list = {
  "IN": "Asia/Kolkata",
  "KR": "Asia/Seoul",
  "GB": "Europe/London",
  "AE": "Asia/Dubai"
}
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
styles = getSampleStyleSheet()
styleN = styles["BodyText"]
styleN.textColor = "#000069"
# from reportlab.platypus import  Image


import datetime
import pdb
import textwrap

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent



# register a custom font
pdfmetrics.registerFont(
    TTFont(
        "barlow-medium",
        os.path.join(BASE_DIR, 'fonts/Barlow-Medium.ttf')
    )
)
pdfmetrics.registerFont(
    TTFont(
        "barlow-regular",
        os.path.join(BASE_DIR, 'fonts/Barlow-Regular.ttf')
    )
)
pdfmetrics.registerFont(
    TTFont(
        "barlow-bold",
        os.path.join(BASE_DIR, 'fonts/Barlow-Bold.ttf')
    )
)
pdfmetrics.registerFont(
    TTFont(
        "barlow-extra_bold",
        os.path.join(BASE_DIR, 'fonts/Barlow-ExtraBold.ttf')
    )
)
pdfmetrics.registerFont(
    TTFont(
        "barlow-semi_bold",
        os.path.join(BASE_DIR, 'fonts/Barlow-SemiBold.ttf')
    )
)

pdfmetrics.registerFont(
    TTFont(
        "Cafe24Simplehae",
        os.path.join(BASE_DIR, 'fonts/Cafe24Simplehae.ttf')
    )
)

# PAGE_WIDTH, PAGE_HEIGHT_ORG = A4
PAGE_WIDTH, PAGE_HEIGHT = A4

assetImageUrl = "http://10.11.56.13/cmms_api/api/uploads/assets/download/"
assetReportImageUrl = (
    "http://10.11.56.13/cmms_api/api/uploads/asset_report/download/"
)



locationImageUrl = (
    "http://10.11.56.13/cmms_api/api/uploads/assets/download/"
)
locationReportImageUrl = (
    "http://10.11.56.13/cmms_api/api/uploads/asset_report/download/"
)


leftMargin = inch * 0.5
rightMargin = inch * 0.5


def sanitize_html(html):
    # Removing unsupported attributes like lang
    cleaned_html = re.sub(r'\s+lang="[^"]*"', '', html)
    return cleaned_html


# //////////////////////////////////////////////////////////// Parse Data for first section ////////////////////////////////////////////////////////////


def parseGeneralInfoAsset(data):
    # pdb.set_trace()

    try:
        cCode = data.get("user").get("phone_no").get("countryCode")
        country_code = timezone_list.get(cCode)
        country_tz = pytz.timezone(country_code)
    except:
        country_code = timezone_list.get("IN")
        country_tz = pytz.timezone(country_code)

        # accDate = datetime.datetime.fromtimestamp(endpoint.get("acceleration", "-").get("Axial", "-").get("timestamp", "-")).astimezone(country_tz).strftime("%m/%d/%y %H:%M")

    assetName = str(data.get("assetName"))
    if len(data.get("endpointRMSData")) > 0:
        try:
            measurementTimestamp = (data.get("endpointRMSData")[0].get("acceleration", "-").get("Axial", "-").get("timestamp", "-"))
            measurementDate = datetime.datetime.fromtimestamp(measurementTimestamp).astimezone(country_tz).strftime("%m/%d/%Y")
        except:
            measurementDate = "-"

    else:
        measurementDate = "No Data Collected Yet"
    try:
        analysisIsoDate = data.get("createdOn", "-")
        analysisDate = datetime.datetime.strptime(analysisIsoDate, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%m/%d/%Y")
    except:
        analysisDate = "-"
    location = str(data.get("locationName", "-"))
    sensorsMapped = str(len(data.get("endpointRMSData")))
    asset_image = data.get("asset_image")

    if data.get("EquipmentHealth") == "1":
        assetCondition = "Critical"
        statusColor = "#FB565A"
        statusTextColor = "#FFFFFF"
    elif data.get("EquipmentHealth") == "2":
        assetCondition = "Danger"
        statusColor = "#FA8349"
        statusTextColor = "#FFFFFF"
    elif data.get("EquipmentHealth") == "3":
        assetCondition = "Alert"
        statusColor = "#F7FA4B"
        statusTextColor = "#000069"
    elif data.get("EquipmentHealth") == "4":
        assetCondition = "Healthy"
        statusColor = "#51FC4C"
        statusTextColor = "#000069"
    elif data.get("EquipmentHealth") == "5":
        assetCondition = "Not Defined"
        statusColor = "#B0B0B0"
        statusTextColor = "#000069"

    return (
        assetName,
        measurementDate,
        analysisDate,
        location,
        sensorsMapped,
        assetCondition,
        asset_image,
        statusColor,
        statusTextColor,
    )


# //////////////////////////////////////////////////////////// Parse Data for readings table ////////////////////////////////////////////////////////////


def parseSensorDataAsset(data):
    # pdb.set_trace()
    try:
        cCode = data.get("user").get("phone_no").get("countryCode")
        print("cCodecCodecCodecCode", cCode)
        country_code = timezone_list.get(cCode)
        country_tz = pytz.timezone(country_code)
    except:
        country_code = timezone_list.get("IN")
        country_tz = pytz.timezone(country_code)

    # dt_country = alarmHistoryData.get("timestamp").astimezone(country_tz).strftime("%b. %d, %Y, %I:%M:%S %p")

    finalData = []
    for endpoint in data.get("endpointRMSData"):
        try:
            # accDate = datetime.datetime.fromtimestamp(endpoint.get("acceleration", "-").get("Axial", "-").get("timestamp", "-")).strftime("%m-%d-%Y %H:%M")
            accDate = datetime.datetime.fromtimestamp(endpoint.get("acceleration", "-").get("Axial", "-").get("timestamp", "-")).astimezone(country_tz).strftime("%m/%d/%y %H:%M")
        except:
            accDate = "-"
        try:
            AARMS = endpoint.get("acceleration", "-").get("Axial", "-").get("rms", "-")
        except:
            AARMS = "-"
        try:
            AHRMS = endpoint.get("acceleration", "-").get("Horizontal", "-").get("rms", "-")
        except:
            AHRMS = "-"
        try:
            AVRMS = endpoint.get("acceleration", "-").get("Vertical", "-").get("rms", "-")
        except:
            AVRMS = "-"
        finalData.append(
            [
                Paragraph(endpoint.get("asset_name") + " > " + endpoint.get("point_name") + "-" + endpoint.get("mount_location"), styleN),
                accDate,
                "Acceleration",
                AVRMS,
                AARMS,
                AHRMS,
            ]
        )
        try:
            # velDate = datetime.datetime.fromtimestamp(endpoint.get("velocity", "-").get("Axial", "-").get("timestamp", "-")).strftime("%m-%d-%Y %H:%M")
            velDate = datetime.datetime.fromtimestamp(endpoint.get("velocity", "-").get("Axial", "-").get("timestamp", "-")).astimezone(country_tz).strftime("%m/%d/%y %H:%M")
        except:
            velDate = "-"
        try:
            VARMS = endpoint.get("velocity", "-").get("Axial", "-").get("rms", "-")
        except:
            VARMS = "-"
        try:
            VHRMS = endpoint.get("velocity", "-").get("Horizontal", "-").get("rms", "-")
        except:
            VHRMS = "-"
        try:
            VVRMS = endpoint.get("velocity", "-").get("Vertical", "-").get("rms", "-")
        except:
            VVRMS = "-"
        finalData.append(
            [
                endpoint.get("point_name") + "-" + endpoint.get("mount_location"),
                velDate,
                "Velocity",
                VVRMS,
                VARMS,
                VHRMS,
            ]
        )
    return finalData


def myFirstPageAsset(canvas, doc, json_data):
    canvas.saveState()
    canvas.setFont("barlow-bold", 16)
    canvas.setFillColor("#000069")
    canvas.drawString(20, PAGE_HEIGHT - inch * 0.75, "Diagnostics Report")
    canvas.setLineWidth(2)
    canvas.setStrokeColor("#F3DDD3")
    canvas.line(10, PAGE_HEIGHT - inch, PAGE_WIDTH - 10, PAGE_HEIGHT - inch)
    canvas.line(10, 0.6 * inch, PAGE_WIDTH - 10, 0.6 * inch)
    canvas.setFont("barlow-regular", 9)
    canvas.setFillColor("#000069")
    canvas.drawString(inch, 0.45 * inch, "Page - %s" % (doc.page))
    canvas.restoreState()

    # /////////////////////////// Add content first rectangle ///////////////////////////
    rect_x = 10
    rect_y = PAGE_HEIGHT - (inch * 3.5)
    rect_width = PAGE_WIDTH / 2
    rect_height = 2.25 * inch

    canvas.saveState()
    canvas.setFont("barlow-regular", 12)
    canvas.setFillColor("#F3DDD3")
    canvas.setStrokeColor("#F3DDD3")
    canvas.roundRect(rect_x, rect_y, rect_width, rect_height, 5, fill=1)
    canvas.restoreState()

    # /////////////////////////// adding text inside rectangle ///////////////////////////
    text = [
        "Asset Name",
        "Measurement Date",
        "Analysis Date",
        "Location",
        "Sensors Mapped",
        "Asset Condition",
    ]

    (
        assetName,
        measurementDate,
        analysisDate,
        location,
        sensorsMapped,
        assetCondition,
        asset_image,
        statusColor,
        statusTextColor,
    ) = parseGeneralInfoAsset(json_data)

    language = detect(assetName)
    
    if language == "ko":
        font_name_updated = "Cafe24Simplehae"
    else:
        font_name_updated = "barlow-regular"
    text2 = [
        assetName,
        measurementDate,
        analysisDate,
        location,
        sensorsMapped,
        assetCondition,
    ]
    # Define the coordinates for the starting position of the text
    text_x = rect_x + 20
    text_y = rect_y + rect_height - 30

    # Define the vertical spacing between rows
    row_spacing = 20

    # Iterate through the text list and draw it in two columns
    canvas.saveState()
    font_name = font_name_updated
    font_size = 12
    canvas.setFont(font_name, font_size)
    canvas.setFillColor("#000069")

    for i in range(len(text)):
        # Draw the text in the left column
        canvas.drawString(text_x, text_y - i * row_spacing, text[i])
        if text[i] == "Asset Condition":
            canvas.setFillColor(statusColor)
            canvas.setStrokeColor(statusColor)
            canvas.roundRect(
                text_x + rect_width / 2,
                text_y - (i + 0.3) * row_spacing,
                (text_x + rect_width / 2) - 80,
                row_spacing,
                5,
                fill=1,
            )
            canvas.setFillColor(statusTextColor)
            canvas.drawString(
                text_x + rect_width / 2 + 5, text_y - i * row_spacing, text2[i]
            )
        else:
            segments = textwrap.wrap(text2[i], 18)
            if len(segments) == 1:
                canvas.drawString(
                    text_x + rect_width / 2, text_y - i * row_spacing, segments[0]
                )
            else:
                canvas.drawString(
                    text_x + rect_width / 2,
                    text_y - i * row_spacing,
                    segments[0] + "...",
                )
            # if len(text2[i]) > 20:
            #     wrap_text = textwrap.wrap(text2[i], width=20)
            #     for single_line in wrap_text:
            #         canvas.drawString(text_x + rect_width / 2, text_y - i * row_spacing, single_line)
            # else:
            #     canvas.drawString(text_x + rect_width / 2, text_y - i * row_spacing, text2[i])
    canvas.restoreState()

    # /////////////////////////// Asset Image ///////////////////////////
    try:
        finalUrl = assetImageUrl + asset_image
        assetImage = ImageReader(finalUrl)
        canvas.drawImage(
            assetImage,
            rect_x + rect_width + 10,
            rect_y,
            rect_width - 30,
            rect_height,
            mask="auto",
        )
    except:
        # pdb.set_trace()
        # canvas.drawCentredString(
        #     rect_x + rect_width * 1.5, rect_y + rect_height / 2, assetName
        # )
        # title_row_spacing = row_spacing
        # if len(assetName) > 40:
        #         wrap_text = textwrap.wrap(assetName, width=40)
        #         for single_line in wrap_text:
        #             canvas.drawCentredString(text_x + rect_width / 2, text_y * row_spacing, single_line)
        #             title_row_spacing += row_spacing
        # else:
        #     canvas.drawCentredString(text_x + rect_width / 2, text_y * row_spacing, assetName)
        canvas.drawCentredString(
            rect_x + rect_width * 1.5, rect_y + rect_height / 2, assetName
        )



def myLaterPages(canvas, doc):
    canvas.saveState()
    canvas.setLineWidth(2)
    canvas.setStrokeColor("#F3DDD3")
    canvas.line(10, 0.6 * inch, PAGE_WIDTH - 10, 0.6 * inch)
    canvas.setFont("barlow-regular", 9)
    canvas.setFillColor("#000069")
    canvas.drawString(PAGE_WIDTH-inch, 0.45 * inch, "Page - %s" % (doc.page-1))
    canvas.restoreState()


# //////////////////////////////////////////////////////////// Asset Health History table ////////////////////////////////////////////////////////////

def parseAssetHealthHistory(json_data):
    status_table = {
        "1": "Critical",
        "2": "Danger",
        "3": "Alert",
        "4": "Healthy",
        "5": "NA"
    }
    data_headers = [[], []]
    for i in json_data.get("asset_health_history"):
        data_headers[0].append(i.get("date"))
        data_headers[1].append(status_table.get(i.get("status")))

    col_width_step = (PAGE_WIDTH - 90) / len(data_headers[0])
    row_height_step = 20
    # Create a table with 4 columns and 4 rows
    table_height = 0
    row_height = []
    col_widths = []
    for i in range(len(data_headers)):
        table_height += row_height_step
        row_height.append(row_height_step)
        col_widths.append(col_width_step)
    table = Table(
        data_headers,
        colWidths=col_widths,
        rowHeights=row_height,

    )

    style = TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.white,
                ),  # set the background color of the header row
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, -1),
                    "#000069",
                ),  # set the text color of all cells
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "barlow-medium",
                ),  # set the font of the all cells
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9,
                ),  # set the font size of all cells
                ("INNERGRID", (0, 0), (-1, -1), 0.2, "#DADADA"),
                ("BOX", (0, 0), (-1, -1), 0.2, "#DADADA"),
                ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),  # align text to vertical centre of cell,
            ]
        )

    colorCodes = {'1': "#FB565A", '2': "#FA8349", '3': "#F7FA4B", '4': "#51FC4C", '5': '#D8DAE2'}
    healthData = json_data.get("asset_health_history", [])
    if len(healthData) > 0:
        for index, data in enumerate(healthData):
            column = index
            row = 1
            style.add(
                "BACKGROUND",
                (column, row),
                (column, row),
                colorCodes.get(data.get("status")),
            )  # Measuring point cell merge with next row
            style.add(
                "PADDING", (column, row), (column, row), 20
            )  # Measuring point cell merge with next row
    
    table.setStyle(style)

    return table

# //////////////////////////////////////////////////////////// Parse latest reading table ////////////////////////////////////////////////////////////


def parseLatestReadingsAsset(json_data):
    # /////////////////////////// Latest Readings section ///////////////////////////
    
    if len(json_data.get("endpointRMSData")) > 0:
        data_headers = [
            ["Measuring Point", "Date", "Field", "RMS"],
            ["", "", "", "Vertical", "Axial", "Horizontal"],
        ]
        sensor_data = parseSensorDataAsset(json_data)
        if len(json_data.get("endpointRMSData")) > 0:
            language = detect(json_data.get("endpointRMSData")[0].get("asset_name"))
            if language == "ko":
                font_name_regular = "Cafe24Simplehae"
                font_name_medium = "Cafe24Simplehae"
            else:
                font_name_regular = "barlow-regular"
                font_name_medium = "barlow-medium"
        else:
            font_name_regular = "barlow-regular"
            font_name_medium = "barlow-medium"

        data = data_headers + sensor_data

        col_width_step = (PAGE_WIDTH - 90) / 9
        row_height_step = 20
        # Create a table with 4 columns and 4 rows
        table_height = 0
        row_height = []
        for i in range(len(data)):
            table_height += row_height_step
            row_height.append(row_height_step)
        table = Table(
            data,
            colWidths=[
                col_width_step * 3,
                col_width_step * 1.5,
                col_width_step * 1.2,
                col_width_step * 1.2,
            ],
            rowHeights=row_height,
        )

        # Set the style of the table
        style = TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.white,
                ),  # set the background color of the header row
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, -1),
                    "#000069",
                ),  # set the text color of all cells
                (
                    "FONTNAME",
                    (1, 2),
                    (-1, -1),
                    font_name_regular,
                ),  # set the font of the value cells
                (
                    "FONTSIZE",
                    (1, 2),
                    (-1, -1),
                    10,
                ),  # set the font size of the value cells
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, 0),
                    12,
                ),  # set the bottom padding of the header row
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, 0),
                    12,
                ),  # set the font size of the header row
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    font_name_medium,
                ),  # set the font of the header row
                (
                    "FONTSIZE",
                    (0, 1),
                    (-1, 1),
                    12,
                ),  # set the font size of the header row
                (
                    "FONTNAME",
                    (0, 1),
                    (-1, 1),
                    font_name_medium,
                ),  # set the font of the header row
                (
                    "FONTSIZE",
                    (0, 0),
                    (0, 0),
                    12,
                ),  # set the font size of the first cell
                (
                    "FONTSIZE",
                    (0, 1),
                    (0, -1),
                    10,
                ),  # set the font size of the first column
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    font_name_medium,
                ),  # set the font of the first column
                (
                    "RIGHTPADDING",
                    (0, 1),
                    (-1, -1),
                    5,
                ),  # set the right padding of the table cells
                ("INNERGRID", (0, 0), (-1, -1), 0.2, "#DADADA"),
                ("BOX", (0, 0), (-1, -1), 0.2, "#DADADA"),
                ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),  # align text to vertical centre of cell,
                ("SPAN", (2, 0), (2, 1)),  # Field cell first row span
                ("SPAN", (3, 0), (-1, 0)),  # RMS cell first row span
            ]
        )
        for i in range(0, len(data), 2):
            style.add(
                "SPAN", (0, i), (0, i + 1)
            )  # Measuring point cell merge with next row
            style.add("SPAN", (1, i), (1, i + 1))  # Date cell merge with next row
        # create the table
        table.setStyle(style)

    else:
        col_width_step = (PAGE_WIDTH - 90) / 9
        table = [["No Data Collected Yet."]]
        table = Table(table, colWidths=[col_width_step], rowHeights=None)
        # Set the style of the table
        style3 = TableStyle(
            [
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, -1),
                    "#000069",
                ),  # set the text color of all cells
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "barlow-regular",
                ),  # set the font of the value cells
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    12,
                ),  # set the font size of the value cells
                ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),  # align text to vertical centre of cell,
            ]
        )
        table.setStyle(style3)

    return table


# //////////////////////////////////////////////////////////// Parse Section heading ////////////////////////////////////////////////////////////


class sectionHeading(Flowable):
    """A simple rectangular shape."""

    def __init__(self, width, height, text_color, text,background_color="#D8DAE2"):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.text_color = colors.HexColor(text_color)
        self.text = text
        self.background_color = background_color

    def __repr__(self):
        return "Rectangle(w=%s, h=%s)" % (self.width, self.height)

    # def draw(self):
    #     self.canv.setFont('barlow-bold', 14)
    #     self.canv.setFillColor(self.text_color)
    #     self.canv.drawCentredString(self.width, self.height, self.text)

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(self.background_color)
        self.canv.setStrokeColor(self.background_color)
        self.canv.roundRect(
            -inch * 0.6,
            self.height * 0.25,
            self.width,
            self.height,
            3,
            stroke=1,
            fill=1,
        )
        self.canv.setFont("barlow-semi_bold", 14)
        self.canv.setFillColor(self.text_color)
        self.canv.drawCentredString(
            (self.width / 2) - inch * 0.6, self.height / 2, self.text
        )
        self.canv.restoreState()

    def wrap(self, availWidth, availHeight):
        # Set the size of the Flowable
        return (self.width, self.height)


# //////////////////////////////////////////////////////////// Parse data for table for faults detected ////////////////////////////////////////////////////////////


def parseFaultData(data):
    faultList = data.get("faultData", [])
    final_data = []
    if len(faultList) > 0:
        for row in faultList:
            final_data.append([row.get("name"), "", "", "", ""])

    return final_data


# //////////////////////////////////////////////////////////// Parse table for faults detected ////////////////////////////////////////////////////////////


def parseFaultTable(json_data):
    data_headers = [
        ["Fault", "Good", "Satisfactory", "Unsatisfactory", "Unacceptable"],
    ]

    fault_data = parseFaultData(json_data)

    # fault_data = [
    #     ["Row 1", "Row 1","Row 1","Row 1","Row 1",],
    #     ["Row 2", "Row 2","Row 2","Row 2","Row 2",],
    #     ["Row 3", "Row 3","Row 3","Row 3","Row 3",],
    #     ["Row 4", "Row 4","Row 4","Row 4","Row 4",],
    # ]

    data = data_headers + fault_data
    col_width_step = (PAGE_WIDTH - inch) / 5
    row_height_step = 20
    table_height = 0
    row_height = []

    for i in range(len(data)):
        table_height += row_height_step
        row_height.append(row_height_step)

    table = Table(
        data,
        colWidths=[
            col_width_step * 1.4,
            col_width_step * 0.9,
            col_width_step * 0.9,
            col_width_step * 0.9,
            col_width_step * 0.9,
        ],
        rowHeights=row_height,
    )

    style = TableStyle(
        [
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                colors.white,
            ),  # set the background color of the header row
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                "#000069",
            ),  # set the text color of all cells
            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                "barlow-medium",
            ),  # set the font of the header row
            ("FONTSIZE", (0, 0), (-1, -1), 12),  # set the font size of the header row
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                12,
            ),  # set the bottom padding of the header row
            ("INNERGRID", (0, 0), (-1, -1), 0.2, "#DADADA"),
            ("BOX", (0, 0), (-1, -1), 0.2, "#DADADA"),
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),  # align text to vertical centre of cell,
            # ('ROUNDEDCORNERS', [2,2,2,2])   # border radius for table
        ]
    )

    colorCodes = {1: "#03B03E", 2: "#F9F500", 3: "#F3B900", 4: "#DF0028"}
    faultData = json_data.get("faultData", [])
    if len(faultData) > 0:
        for index, data in enumerate(faultData):
            column = data.get("value")
            row = index + 1
            style.add(
                "BACKGROUND",
                (column, row),
                (column, row),
                colorCodes.get(data.get("value")),
            )  # Measuring point cell merge with next row
            style.add(
                "PADDING", (column, row), (column, row), 20
            )  # Measuring point cell merge with next row
    table.setStyle(style)

    return table


# //////////////////////////////////////////////////////////// Parse attachments/images ////////////////////////////////////////////////////////////


def parseAttachments(data):
    imageList = []

    try:
        attachment_list = data.get("files").get("attachments")
    except:
        attachment_list = []

    if len(attachment_list) > 0:
        for row in attachment_list:
            image = assetReportImageUrl + row.get("name")
            imageList.append(Image(image, width=PAGE_WIDTH - inch, height=2.5 * inch))
            imageList.append(Spacer(1, 0.1 * inch))

    return imageList


def parseNoAttachment():
    col_width_step = (PAGE_WIDTH - 90) / 9
    tableData = [["No files attached."]]
    table = Table(tableData, colWidths=[col_width_step], rowHeights=None)
    # Set the style of the table
    style3 = TableStyle(
        [
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                "#000069",
            ),  # set the text color of all cells
            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                "barlow-regular",
            ),  # set the font of the value cells
            ("FONTSIZE", (0, 0), (-1, -1), 12),  # set the font size of the value cells
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),  # align text to vertical centre of cell,
        ]
    )
    table.setStyle(style3)
    return table


# //////////////////////////////////////////////////////////// Parse Observations ////////////////////////////////////////////////////////////


def parseObservations(data):
    text_raw = data.get("Observations")
    text = text_raw.replace("<br>", "<br/>")
    sanitized_html_text = sanitize_html(text)
    language = detect(text)
    if language == "ko":
        font_name = "Cafe24Simplehae"
    else:
        font_name = "barlow-regular"

    styles = ParagraphStyle(
        name="my_style",
        fontName=font_name,
        borderWidth=0.5,
        borderRadius=3,
        borderPadding=10,
        backColor="#F7F8F9",
        minHeight=3 * inch,
        borderColor="#F7F8F9",
    )
    # style = styles["Normal"]
    p = Paragraph(sanitized_html_text, styles)

    return p


# //////////////////////////////////////////////////////////// Parse Recommendations ////////////////////////////////////////////////////////////


def parseRecommendations(data):
    text_raw = data.get("Recommendations")
    text = text_raw.replace("<br>", "<br/>")
    sanitized_html_text = sanitize_html(text)
    language = detect(text)
    
    if language == "ko":
        font_name = "Cafe24Simplehae"
    else:
        font_name = "barlow-regular"

    styles = ParagraphStyle(
        name="my_style",
        fontName=font_name,
        borderWidth=0.5,
        borderRadius=3,
        borderPadding=10,
        backColor="#F7F8F9",
        minHeight=3 * inch,
        borderColor="#F7F8F9",
    )
    p = Paragraph(sanitized_html_text, styles)

    return p


# //////////////////////////////////////////////////////////// Generate Asset PDF ////////////////////////////////////////////////////////////


@api_view(["GET", "POST"])
def generate_asset_report(request):
    # styles = getSampleStyleSheet()

    # try:
    raw_data = JSONParser().parse(request)
    if not raw_data:
        return Response(
            {"message": "Json Data not found."}, status=status.HTTP_404_NOT_FOUND
        )

    json_data = raw_data.get("data")
    print("json_data.get", json_data.get("accountId"))


    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="{0}"'.format(
        json_data.get("assetName")
    )
    doc = SimpleDocTemplate(response, pagesize=A4)
    Story = [Spacer(1, 3 * inch)]

    # ////////////////// Asset Health History table //////////////////
    if json_data.get("asset_health_history"):
        healthHistoryHeading = sectionHeading(
            width=PAGE_WIDTH - inch,
            height=0.3 * inch,
            text_color="#000069",
            text="Asset Health History",
        )  # heading of the section
        Story.append(healthHistoryHeading)
        Story.append(Spacer(1, 0.1 * inch))
        # add asset health history trend here
        healthHistoryTable = parseAssetHealthHistory(json_data) # Asset Health History table
        Story.append(healthHistoryTable)

        verticalSpacer = Spacer(1, 0.5 * inch)
        Story.append(verticalSpacer)

    # ////////////////// Latest reading table //////////////////
    readingHeading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.3 * inch,
        text_color="#000069",
        text="Latest Readings",
    )  # heading of the section
    Story.append(readingHeading)
    Story.append(Spacer(1, 0.1 * inch))
    readingTable = parseLatestReadingsAsset(json_data)  # Latest reading table
    Story.append(readingTable)

    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)

    # ////////////////// Faults detected table //////////////////
    faultHeading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.3 * inch,
        text_color="#000069",
        text="Faults Detected",
    )  # heading of the section
    Story.append(faultHeading)
    Story.append(Spacer(1, 0.1 * inch))
    faultTable = parseFaultTable(json_data)
    Story.append(faultTable)

    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)

    # ////////////////// attachments //////////////////
    attachmentsHeading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.3 * inch,
        text_color="#000069",
        text="Attachments",
    )  # heading of the section
    Story.append(attachmentsHeading)
    Story.append(Spacer(1, 0.1 * inch))
    if len(json_data.get("files")) > 0:
        attachments = parseAttachments(json_data)
        Story.extend(attachments)
    else:
        noAttachment = parseNoAttachment()
        Story.append(noAttachment)

    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)

    # ////////////////// Observations //////////////////
    observationHeading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.3 * inch,
        text_color="#000069",
        text="Observations",
    )  # heading of the section
    Story.append(observationHeading)
    Story.append(Spacer(1, 0.3 * inch))
    observations = parseObservations(json_data)
    Story.append(observations)

    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)

    # ////////////////// Recommendations //////////////////
    recommendationsHeading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.3 * inch,
        text_color="#000069",
        text="Recommendations",
    )  # heading of the section
    Story.append(recommendationsHeading)
    Story.append(Spacer(1, 0.3 * inch))
    recommendations = parseRecommendations(json_data)
    Story.append(recommendations)

    doc.build(
        Story,
        onFirstPage=lambda canvas, doc: myFirstPageAsset(canvas, doc, json_data),
        onLaterPages=myLaterPages,
    )

    return response


# except:
# return Response({'message':'Something is wrong with the data. Please contact admin'}, status=status.HTTP_404_NOT_FOUND)


# //////////////////////////////////////////////////////////// Generate Location PDF ////////////////////////////////////////////////////////////


# *************************************************** Parse Data for first section ***************************************************


def parseGeneralInfoLocation(data):
    # pdb.set_trace()
    locationName = str(data.get("location_name"))
    creationDate = data.get("created_on")
    noOfAssets = len(data.get("asset_report_data"))
    location_image = data.get("location_image")

    return locationName, creationDate, str(noOfAssets), location_image


def myFirstPageLocation(canvas, doc, json_data):
    canvas.saveState()
    canvas.setFont("barlow-bold", 16)
    canvas.setFillColor("#000069")
    canvas.drawString(
        20, PAGE_HEIGHT - inch * 0.75, "Predictive Maintenance Summary Report"
    )
    canvas.setLineWidth(2)
    canvas.setStrokeColor("#F3DDD3")
    canvas.line(10, PAGE_HEIGHT - inch, PAGE_WIDTH - 10, PAGE_HEIGHT - inch)
    canvas.line(10, 0.6 * inch, PAGE_WIDTH - 10, 0.6 * inch)
    canvas.setFont("barlow-regular", 9)
    canvas.setFillColor("#000069")
    canvas.drawString(inch, 0.45 * inch, "Page - %s" % (doc.page))
    canvas.restoreState()

    # /////////////////////////// Add content first rectangle ///////////////////////////
    rect_x = 10
    rect_y = PAGE_HEIGHT - (inch * 3.5)
    rect_width = PAGE_WIDTH / 2
    rect_height = 2.25 * inch

    canvas.saveState()
    canvas.setFont("barlow-regular", 12)
    canvas.setFillColor("#F3DDD3")
    canvas.setStrokeColor("#F3DDD3")
    canvas.roundRect(rect_x, rect_y, rect_width, rect_height, 5, fill=1)
    canvas.restoreState()

    # /////////////////////////// adding text inside rectangle ///////////////////////////
    text = ["Location Name", "Creation Date", "Total number of Assets"]

    locationName, creationDate, noOfAssets, location_image = parseGeneralInfoLocation(
        json_data
    )

    text2 = [locationName, creationDate, noOfAssets, location_image]
    # Define the coordinates for the starting position of the text
    text_x = rect_x + 20
    text_y = rect_y + rect_height - 30

    # Define the vertical spacing between rows
    row_spacing = 20

    # Iterate through the text list and draw it in two columns
    canvas.saveState()
    font_name = "barlow-regular"
    font_size = 12
    canvas.setFont(font_name, font_size)
    canvas.setFillColor("#000069")

    for i in range(len(text)):
        # Draw the text in the left column
        canvas.drawString(text_x, text_y - i * row_spacing, text[i])
        segments = textwrap.wrap(text2[i], 18)
        if len(segments) == 1:
            canvas.drawString(
                text_x + rect_width / 2, text_y - i * row_spacing, segments[0]
            )
        else:
            canvas.drawString(
                text_x + rect_width / 2, text_y - i * row_spacing, segments[0] + "..."
            )
    canvas.restoreState()

    # /////////////////////////// Asset Image ///////////////////////////
    try:
        finalUrl = locationImageUrl + location_image
        assetImage = ImageReader(finalUrl)
        canvas.drawImage(
            assetImage,
            rect_x + rect_width + 10,
            rect_y,
            rect_width - 30,
            rect_height,
            mask="auto",
        )
    except:
        canvas.drawCentredString(
            rect_x + rect_width * 1.5, rect_y + rect_height / 2, locationName
        )


# *************************************************** Parse Data for Asset Readings ***************************************************


def parseSensorDataAssetLocation(data, country_tz):


    finalData = []
    for endpoint in data.get("endpointRMSData"):
        try:
            # accDate = datetime.datetime.fromtimestamp(endpoint.get("acceleration", "-").get("Axial", "-").get("timestamp", "-")).strftime("%m/%d/%Y %H:%M")
            accDate =   datetime.datetime.fromtimestamp(endpoint.get("acceleration", "-").get("Axial", "-").get("timestamp", "-")).astimezone(country_tz).strftime("%m/%d/%y %H:%M")
        except:
            accDate = "-"
        try:
            AARMS = endpoint.get("acceleration", "-").get("Axial", "-").get("rms", "-")
        except:
            AARMS = "-"
        try:
            AHRMS = (
                endpoint.get("acceleration", "-").get("Horizontal", "-").get("rms", "-")
            )
        except:
            AHRMS = "-"
        try:
            AVRMS = (
                endpoint.get("acceleration", "-").get("Vertical", "-").get("rms", "-")
            )
        except:
            AVRMS = "-"
        finalData.append(
            [
                Paragraph(endpoint.get("asset_name", "-") + " > " + endpoint.get("point_name", "--") + "-" + endpoint.get("mount_location", "---"), styleN),
                accDate,
                "Acceleration",
                AVRMS,
                AARMS,
                AHRMS,
            ]
        )
        try:
            # velDate = datetime.datetime.fromtimestamp(endpoint.get("velocity", "-").get("Axial", "-").get("timestamp", "-")).strftime("%m/%d/%Y %H:%M")
            velDate =   datetime.datetime.fromtimestamp(endpoint.get("velocity", "-").get("Axial", "-").get("timestamp", "-")).astimezone(country_tz).strftime("%m/%d/%y %H:%M")
        except:
            velDate = "-"
        try:
            VARMS = endpoint.get("velocity", "-").get("Axial", "-").get("rms", "-")
        except:
            VARMS = "-"
        try:
            VHRMS = endpoint.get("velocity", "-").get("Horizontal", "-").get("rms", "-")
        except:
            VHRMS = "-"
        try:
            VVRMS = endpoint.get("velocity", "-").get("Vertical", "-").get("rms", "-")
        except:
            VVRMS = "-"
        finalData.append(
            [
                endpoint.get("point_name") + "-" + endpoint.get("mount_location"),
                velDate,
                "Velocity",
                VVRMS,
                VARMS,
                VHRMS,
            ]
        )
    return finalData


# *************************************************** Parse Table for No Data Found ***************************************************

class getErrorMessage(Flowable):
    """A simple rectangular shape."""

    def __init__(self, width, height, text_color, text,background_color="#FFFFFF"):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.text_color = colors.HexColor(text_color)
        self.text = text
        self.background_color = background_color

    def __repr__(self):
        return "Rectangle(w=%s, h=%s)" % (self.width, self.height)

    # def draw(self):
    #     self.canv.setFont('barlow-bold', 14)
    #     self.canv.setFillColor(self.text_color)
    #     self.canv.drawCentredString(self.width, self.height, self.text)

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(self.background_color)
        self.canv.setStrokeColor(self.background_color)
        self.canv.roundRect(
            -inch * 0.6,
            self.height * 0.25,
            self.width,
            self.height,
            3,
            stroke=1,
            fill=1,
        )
        self.canv.setFont("barlow-regular", 12)
        self.canv.setFillColor(self.text_color)
        self.canv.drawCentredString(
            (self.width / 2) - inch * 0.6, self.height / 2, self.text
        )
        self.canv.restoreState()

    def wrap(self, availWidth, availHeight):
        # Set the size of the Flowable
        return (self.width, self.height)


# *************************************************** Parse Table for Asset Readings ***************************************************

def parseLatestReadingsLocation(json_data, country_tz):
    # /////////////////////////// Latest Readings section ///////////////////////////

    data_headers = [
        ["Vibration Readings"],
        ["Measuring Point", "Date", "Field", "RMS"],
        ["", "", "", "Vertical", "Axial", "Horizontal"],
    ]

    sensor_data = parseSensorDataAssetLocation(json_data, country_tz)

    data = data_headers + sensor_data

    col_width_step = (PAGE_WIDTH - 90) / 9
    row_height_step = 20
    # Create a table with 4 columns and 4 rows
    table_height = 0
    row_height = []
    for i in range(len(data)):
        table_height += row_height_step
        row_height.append(row_height_step)
    table = Table(
        data,
        colWidths=[
            col_width_step * 3,
            col_width_step * 1.5,
            col_width_step * 1.2,
            col_width_step * 1.2,
        ],
        rowHeights=row_height,
    )

    # Set the style of the table
    # Set the style of the table
    style = TableStyle(
        [
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                colors.white,
            ),  # set the background color of the header row
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                "#000069",
            ),  # set the text color of all cells
            (
                "FONTNAME",
                (1, 2),
                (-1, -1),
                "barlow-regular",
            ),  # set the font of the value cells
            ("FONTSIZE", (1, 2), (-1, -1), 10),  # set the font size of the value cells
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, 0),
                12,
            ),  # set the bottom padding of the header row
            ("FONTSIZE", (0, 0), (-1, 0), 12),  # set the font size of the header row
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "barlow-medium",
            ),  # set the font of the header row
            ("FONTSIZE", (0, 1), (-1, 1), 12),  # set the font size of the header row
            (
                "FONTNAME",
                (0, 1),
                (-1, 1),
                "barlow-medium",
            ),  # set the font of the header row
            ("FONTSIZE", (0, 0), (0, 0), 12),  # set the font size of the first column
            ("FONTSIZE", (0, 1), (0, -1), 10),  # set the font size of the first column
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "barlow-medium",
            ),  # set the font of the first column
            (
                "RIGHTPADDING",
                (0, 1),
                (-1, -1),
                5,
            ),  # set the right padding of the table cells
            ("INNERGRID", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("BOX", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),  # align text to vertical centre of cell,
            ("SPAN", (2, 1), (2, 2)),  # Field cell second row span
            ("SPAN", (3, 1), (-1, 1)),  # RMS cell second row span
            ("SPAN", (0, 0), (-1, 0)),  # RMS cell first row span
        ]
    )
    for i in range(1, len(data), 2):
        style.add(
            "SPAN", (0, i), (0, i + 1)
        )  # Measuring point cell merge with next row
        style.add("SPAN", (1, i), (1, i + 1))  # Date cell merge with next row
    # create the table
    table.setStyle(style)


    return table


def parseAssetHealthTrend(df):
    # pdb.set_trace()

    asset_health_table = []
    statusDict = {"1": "Critical", "2": "Danger", "3": "Alert" , "4": "Healthy", "5": "NA"}

        # Set the style of the table
    style = TableStyle(
        [
            ("BACKGROUND",(0, 0),(-1, -1),colors.white,),  # set the background color of the header row
            ("TEXTCOLOR",(0, 0),(-1, -1),"#000069",),  # set the text color of all cells
            # ("FONTNAME",(1, 0),(-1, -1),"barlow-regular",),  # set the font of the value cells
            # ("FONTSIZE", (1, 0), (-1, -1), 10),  # set the font size of the value cells
            ("INNERGRID", (0, 0), (-1, -1), 0.2, "#DADADA"),
            ("BOX", (0, 0), (-1, -1), 0.2, "#DADADA"),
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            ("VALIGN",(0, 0),(-1, -1),"MIDDLE"),  # align text to vertical centre of cell,
            ("FONTSIZE", (0, 0), (-1,-1), 10),  # set the font size of the header
            ("FONTNAME", (0, 0), (-1,-1), "barlow-regular"),  # set the font of the header
        ]
    )

    colorCodes = {"1": "#FB565A", "2": "#FA8349", "3": "#F7FA4B", "4": "#51FC4C", "5": "#d8dae2"}
    data_header1 = []
    row1 = [a.get("date") for a in df[0].get("dummyList")]
    row1.insert(0, "Equipment")
    data_header1.append(row1)

    row_index = 1
    for i in df:
        row2 = [statusDict.get(j.get("status")) for j in i.get("asset_health_history")]
        row2.insert(0, i.get("asset_name"))
        data_header1.append(row2)
        for index, data in enumerate(i.get("asset_health_history")):
            column = index + 1
            row = row_index
            style.add(
                "BACKGROUND",
                (column, row),
                (column, row),
                colorCodes.get(data.get("status")),
            )  # Measuring point cell merge with next row
            style.add(
                "PADDING", (column, row), (column, row), 20
            )  # Measuring point cell merge with next row
        row_index += 1


    col_width_step = (PAGE_WIDTH - 90) / (len(df[0].get("dummyList"))+1)
    col_width = [col_width_step for i in range(len(df[0].get("dummyList"))+1)]

    data1 = data_header1

    table1 = Table(
        data1, colWidths=col_width, rowHeights=None
    )

    # create the table
    table1.setStyle(style)
    asset_health_table.append(table1)

    return asset_health_table


# *************************************************** Parse Asset Detail reading table ***************************************************


def parseAssetDetailLocation(df, country_tz):
    # /////////////////////////// Latest Readings section ///////////////////////////

    single_asset_tables = []

    # ////////////// Parsing First Table //////////////

    col_width_step = (PAGE_WIDTH - 90) / 9

    data_header1 = [["", ""]]
    table_data1 = [
        ["Equipment Name", Paragraph(df.get("asset_name"))],
        ["Observations", Paragraph(df.get("observations"))],
        ["Recommendations", Paragraph(df.get("recommendations"))],
    ]

    
    if detect(df.get("asset_name")) or detect(df.get("observations")) or detect(df.get("recommendations"))  == "ko":
        font_name_regular = "Cafe24Simplehae"
        font_name_medium = "Cafe24Simplehae"
    else:
        font_name_regular = "barlow-regular"
        font_name_medium = "barlow-medium"

    data1 = data_header1 + table_data1

    # Create a table with 2 columns and 4 rows
    table1 = Table(
        data1, colWidths=[col_width_step * 2, col_width_step * 7], rowHeights=None
    )

    # Set the style of the table
    style = TableStyle(
        [
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                colors.white,
            ),  # set the background color of the header row
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                "#000069",
            ),  # set the text color of all cells
            (
                "FONTNAME",
                (1, 0),
                (-1, -1),
                font_name_regular,
            ),  # set the font of the value cells
            ("FONTSIZE", (1, 0), (-1, -1), 10),  # set the font size of the value cells
            ("INNERGRID", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("BOX", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),  # align text to vertical centre of cell,
            ("SPAN", (0, 0), (1, 0)),  # merge cols of first row
            ("FONTSIZE", (0, 0), (1, 0), 12),  # set the font size of the header
            ("FONTNAME", (0, 0), (1, 0), font_name_medium),  # set the font of the header
        ]
    )
    # create the table
    table1.setStyle(style)

    single_asset_tables.append(table1)
    single_asset_tables.append(Spacer(1, 0.15 * inch))

    # ////////////// Parsing Second Table //////////////

    faultLevelDict = {
        1: "Not Detected",
        2: "Satisfactory",
        3: "Un-satisfactory",
        4: "Un-acceptable",
    }

    data_header2 = [["Faults Detected", "", ""], ["Fault Type", "Severity Level", ""]]
    table_data2 = []
    for fault in df.get("fault_data"):
        image = 'media/'+str(fault.get("value"))+'.png'
        table_data2.append(
            [
                fault.get("name"),
                faultLevelDict.get(fault.get("value")),
                Image(image, width=col_width_step * 0.8, height=20),
            ]
        )
    data2 = data_header2 + table_data2

    # Create a table with 2 columns and dynamic rows
    table2 = Table(
        data2, colWidths=[col_width_step * 2, col_width_step * 3], rowHeights=None
    )

    # Set the style of the table
    style2 = TableStyle(
        [
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                colors.white,
            ),  # set the background color of the header row
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                "#000069",
            ),  # set the text color of all cells
            (
                "FONTNAME",
                (1, 0),
                (-1, -1),
                "barlow-regular",
            ),  # set the font of the value cells
            ("FONTSIZE", (1, 0), (-1, -1), 10),  # set the font size of the value cells
            ("INNERGRID", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("BOX", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),  # align text to vertical centre of cell,
            ("SPAN", (0, 0), (2, 0)),  # merge cols of first row
            ("SPAN", (1, 1), (2, 1)),  # merge cols of second row
            ("FONTSIZE", (0, 0), (1, 0), 12),  # set the font size of the header
            ("FONTNAME", (0, 0), (1, 0), "barlow-medium"),  # set the font of the header
        ]
    )

    table2.setStyle(style2)
    single_asset_tables.append(table2)
    single_asset_tables.append(Spacer(1, 0.15 * inch))

    # ////////////// Parsing Third Table //////////////

    if len(df.get("endpointRMSData")) > 0:
        readingTable = parseLatestReadingsLocation(df, country_tz)
        single_asset_tables.append(readingTable)
    else:
        table_data3 = [["Vibration Readings"], ["No Data Collected Yet."]]
        table3 = Table(table_data3, colWidths=[col_width_step], rowHeights=None)
        # Set the style of the table
        style3 = TableStyle(
            [
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, -1),
                    "#000069",
                ),  # set the text color of all cells
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "barlow-regular",
                ),  # set the font of the value cells
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, 0),
                    12,
                ),  # set the font size of the value cells
                (
                    "FONTSIZE",
                    (0, 1),
                    (-1, 1),
                    10,
                ),  # set the font size of the value cells
                ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),  # align text to vertical centre of cell,
            ]
        )
        table3.setStyle(style3)
        single_asset_tables.append(table3)

    return single_asset_tables


# *************************************************** Parse Asset Condition Summary Bar Graph ***************************************************
def parseAssetConditionBarGraph(df,height=100,width=220):
    drawing = Drawing(height, width)

    data_set = []
    categories = []
    colorCodes = []
    for row in df:
        data_set.append(row.get("value").get("value"))
        categories.append(row.get("key"))
        colorCodes.append(row.get("value").get("itemStyle").get("color"))

    data = tuple(data_set)

    bc = VerticalBarChart()
    bc.x = 20
    bc.y = 50
    bc.height = 140
    bc.width = 400
    bc.data = [data]
    # bc.strokeColor = colors.black
    bc.barLabels.fontName = "Helvetica"
    bc.barLabels.fontSize = 10
    bc.barLabels.fillColor = colors.black
    bc.barLabelFormat = '%d'
    bc.barLabels.nudge = 7
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(data_set) + 1
    bc.valueAxis.valueStep = 1

    bc.categoryAxis.labels.boxAnchor = "ne"
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 30
    bc.categoryAxis.categoryNames = categories
    bc.categoryAxis.labels.fontName = "barlow-medium"
    bc.barWidth = 5
    bc.bars[(0, 0)].fillColor = colors.HexColor(colorCodes[0])
    bc.bars[(0, 0)].strokeColor = colors.HexColor(colorCodes[0])
    bc.bars[(0, 1)].fillColor = colors.HexColor(colorCodes[1])
    bc.bars[(0, 1)].strokeColor = colors.HexColor(colorCodes[1])
    bc.bars[(0, 2)].fillColor = colors.HexColor(colorCodes[2])
    bc.bars[(0, 2)].strokeColor = colors.HexColor(colorCodes[2])
    bc.bars[(0, 3)].fillColor = colors.HexColor(colorCodes[3])
    bc.bars[(0, 3)].strokeColor = colors.HexColor(colorCodes[3])
    bc.bars[(0, 4)].fillColor = colors.HexColor(colorCodes[4])
    bc.bars[(0, 4)].strokeColor = colors.HexColor(colorCodes[4])

    drawing.add(bc)

    return drawing


# *************************************************** Parse Asset Fault Summary Bar Graph ***************************************************
def parseAssetFaultBarGraph(df,height=100,width=220):
    drawing = Drawing(height, width)

    data_set = []
    categories = []
    colorCodes = [
        "#5A78D4",
        "#91CC75",
        "#FAC858",
        "#EE6666",
        "#73C0DE",
        "#3BA272",
        "#D8DAE2",
    ]
    for row in df:
        data_set.append(row.get("value"))
        categories.append(row.get("key"))

    data = tuple(data_set)

    bc = VerticalBarChart()
    bc.x = 20
    bc.y = 50
    bc.height = 140
    bc.width = 400
    bc.data = [data]

    bc.barLabels.fontName = "Helvetica"
    bc.barLabels.fontSize = 10
    bc.barLabels.fillColor = colors.black
    bc.barLabelFormat = '%d'
    bc.barLabels.nudge =7
    # bc.strokeColor = colors.black

    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(data_set) + 1
    bc.valueAxis.valueStep = 1

    bc.categoryAxis.labels.boxAnchor = "ne"
    bc.categoryAxis.labels.dx = 8
    bc.categoryAxis.labels.dy = -2
    bc.categoryAxis.labels.angle = 30
    bc.categoryAxis.categoryNames = categories
    bc.categoryAxis.labels.fontName = "barlow-medium"
    bc.barWidth = 5
    bc.bars[(0, 0)].fillColor = colors.HexColor(colorCodes[0])
    bc.bars[(0, 0)].strokeColor = colors.HexColor(colorCodes[0])
    bc.bars[(0, 1)].fillColor = colors.HexColor(colorCodes[1])
    bc.bars[(0, 1)].strokeColor = colors.HexColor(colorCodes[1])
    bc.bars[(0, 2)].fillColor = colors.HexColor(colorCodes[2])
    bc.bars[(0, 2)].strokeColor = colors.HexColor(colorCodes[2])
    bc.bars[(0, 3)].fillColor = colors.HexColor(colorCodes[3])
    bc.bars[(0, 3)].strokeColor = colors.HexColor(colorCodes[3])
    bc.bars[(0, 4)].fillColor = colors.HexColor(colorCodes[4])
    bc.bars[(0, 4)].strokeColor = colors.HexColor(colorCodes[4])
    bc.bars[(0, 5)].fillColor = colors.HexColor(colorCodes[5])
    bc.bars[(0, 5)].strokeColor = colors.HexColor(colorCodes[5])
    bc.bars[(0, 6)].fillColor = colors.HexColor(colorCodes[6])
    bc.bars[(0, 6)].strokeColor = colors.HexColor(colorCodes[6])

    drawing.add(bc)

    return drawing



healthFlagToColorImage = {
    "1":'<img src="media/asset_health_status/white.png" width="20" height="20" />  <img src="media/asset_health_status/1.png" width="10" height="10" />  ',
    "2":'<img src="media/asset_health_status/white.png" width="20" height="20" />  <img src="media/asset_health_status/2.png" width="10" height="10" />  ',
    "3":'<img src="media/asset_health_status/white.png" width="20" height="20" />  <img src="media/asset_health_status/3.png" width="10" height="10" />  ',
    "4":'<img src="media/asset_health_status/white.png" width="20" height="20" />  <img src="media/asset_health_status/4.png" width="10" height="10" />  ',
    "5":'<img src="media/asset_health_status/white.png" width="20" height="20" />  <img src="media/asset_health_status/5.png" width="10" height="10" />  ',
}
    



@api_view(["GET", "POST"])
def generate_location_report(request):
    styles = getSampleStyleSheet()

    # try:
    # pdb.set_trace()
    raw_data = JSONParser().parse(request)
    if not raw_data:
        return Response(
            {"message": "Json Data not found."}, status=status.HTTP_404_NOT_FOUND
        )
    json_data = raw_data.get("data")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="{0}"'.format(
        json_data.get("assetName")
    )

    class PdfDocument(SimpleDocTemplate):
        def __init__(self, filename, **kw):
            self.allowSplitting = 0
            SimpleDocTemplate.__init__(self, filename=filename, **kw)


        def afterFlowable(self, flowable):
            if flowable.__class__.__name__ == "Paragraph":
                text = flowable.getPlainText()
                style = flowable.style.name
                if style == 'Heading1':

                    toc_el = [ 1,  text, self.page ] # basic elements
                
                    self.notify('TOCEntry', (0, flowable.text, self.page))
                if style == 'Heading2':
                    key = 'h2-%s' % self.seq.nextf('heading2')
                    self.canv.bookmarkPage(key)
                    toc_el = [ 1,  text, self.page ] # basic elements
                    self.notify('TOCEntry', (1, flowable.text, self.page, key))

                    # self.notify('TOCEntry', tuple(toc_el))
            


    doc = PdfDocument(response, pagesize=A4)
    Story = [Spacer(1,  inch)]
    cover_image=Image("media/logo/presageLogo.png", width=400, height=100)
    # cover_image.width = 100  # Set the width to 200 units
    # cover_image.height = 300 
    Story.append(cover_image)


    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)
    ge_heading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.5 * inch,
        text_color="#ffffff",
        text="GLOBAL REPORT",
        background_color="#000000",
    )

  # /////////////////////////// Latest Readings section ///////////////////////////

    single_asset_tables = []

    # ////////////// Parsing First Table //////////////

    col_width_step = (PAGE_WIDTH - 90) / 9
    cDate = json_data.get("created_on")
    dt = cDate.split("T")[0]
    dtt = datetime.date.fromisoformat(dt)
    formatted_datetime = dtt.strftime("%b-%d-%Y")

    uName = json_data.get("user").get("firstName") + " " + json_data.get("user").get("lastName")

    data_header1 = [["", ""]]
    table_data1 = [
        ["Prepared By ","Approved By " ,"Date"],
        [uName, uName,formatted_datetime],
    ]

    data1 = data_header1 + table_data1

    # Create a table with 3 columns and 2 rows
    table1 = Table(
        data1, colWidths=[col_width_step * 3,col_width_step * 3, col_width_step* 2], rowHeights=None
    )

    # Set the style of the table
    style = TableStyle(
        [
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                colors.white,
            ),  # set the background color of the header row
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                "#000069",
            ),  # set the text color of all cells
            (
                "FONTNAME",
                (1, 0),
                (-1, -1),
                "barlow-regular",
            ),  # set the font of the value cells
            ("FONTSIZE", (1, 0), (-1, -1), 10),  # set the font size of the value cells
            ("INNERGRID", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("BOX", (0, 1), (-1, -1), 0.2, "#DADADA"),
            ("ALIGN", (0, 0), (-1, -1), "CENTRE"),  # align text to start of cell
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),  # align text to vertical centre of cell,
            ("SPAN", (0, 0), (1, 0)),  # merge cols of first row
            ("FONTSIZE", (0, 0), (1, 0), 12),  # set the font size of the header
            ("FONTNAME", (0, 0), (1, 0), "barlow-medium"),  # set the font of the header
        ]
    )
    # create the table
    table1.setStyle(style)

    cover_image=Image("media/logo/presageLogo.png", width=100, height=25)
    # cover_image.width = 20  # Set the width to 200 units
    # cover_image.height = 10
    Story.append(ge_heading)
    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)
    Story.append(cover_image)
    Story.append(table1)
    verticalSpacer = Spacer(1, 0.5 * inch)
    Story.append(verticalSpacer)
    # single_asset_tables.append(Spacer(1, 0.15 * inch))

    # t.setStyle(TableStyle())
    # Story.append(t)


    

    Story.append(PageBreak())
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(fontName='barlow-medium', fontSize=14, name='Heading1',
                       leftIndent=20, firstLineIndent=-20, spaceBefore=5,
                       leading=16),
        ParagraphStyle(fontName='barlow-medium', fontSize=14, name='Heading2',
                           leftIndent=20, firstLineIndent=-20, spaceBefore=5,
                           leading=16),
    ]
    
    styles = getSampleStyleSheet()


    toc_heading = sectionHeading(
        width=PAGE_WIDTH - inch,
        height=0.3 * inch,
        text_color="#000069",
        text="Table of Contents",
    )  # heading of the section
    Story.append(toc_heading)

    Story.append(toc)
    Story.append(PageBreak())

    
    # ////////////////// Adding Asset Condition Summary Data //////////////////
    
    
    # doHeading("Chapter 1 - Gobal Table", styles["Heading1"])
    para = Paragraph('<a name="{}"></a>{}'.format("global",  '<a href="#{}">{}</a>'.format("global", 'Overall - Summary')), style=styles['Heading1'])

    # para = Paragraph(<a name="apple"/>', style=styles['Heading1'])
    
    # doHeading('Chapter 1 - Gobal Table', styles['Heading1'])
    barGraphHeading1 = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Asset Condition Summary Data") 
    toc.addEntry(0,'<a href="#{}">{}</a>'.format("global", 'Overall - Summary'), 1)

    # toc.addEntry(0, Paragraph(, style=styles['Heading1']), 1)
    Story.append(para)
    Story.append(Spacer(1, 0.5 * inch))
    Story.append(barGraphHeading1)
    # Story.append(Spacer(1, 0.1 * inch))
    firstBarGraph = parseAssetConditionBarGraph(json_data.get("asset_condition_summary_data"))
    Story.append(firstBarGraph)

    verticalSpacer = Spacer(1, 1 * inch)
    Story.append(verticalSpacer)

    # ////////////////// Adding Asset Fault Summary Data //////////////////
    barGraphHeading2 = sectionHeading( width=PAGE_WIDTH - inch, height=0.3 * inch, text_color="#000069", text="Asset Fault Summary Data")  # heading of the section
    toc.addEntry(0, 'The Beginning', 1)
    Story.append(barGraphHeading2)
    # Story.append(Spacer(1, 0.1 * inch))
    secondBarGraph = parseAssetFaultBarGraph(json_data.get("asset_fault_summary_data"))
    Story.append(secondBarGraph)

    # Story.append(verticalSpacer)
    Story.append(PageBreak())
    # ////////////////// Latest reading table //////////////////
    # readingHeading = sectionHeading(width=PAGE_WIDTH - inch,height=0.3 * inch,text_color="#000069",text="Location Brief Summary Report")  # heading of the section
    # Story.append(readingHeading)
    Story.append(Spacer(1, 0.1 * inch))
    toc.addEntry(0, 'Repost datab', 2)

    # ////////////////////////////////// Country code for timestamp parsing //////////////////////////////////
    try:
        cCode = json_data.get("user").get("phone_no").get("countryCode")
        country_code = timezone_list.get(cCode)
        country_tz = pytz.timezone(country_code)
    except:
        country_code = timezone_list.get("IN")
        country_tz = pytz.timezone(country_code)
    
    cout = 2
    for sub_location_data in json_data.get("sub_location_data"):
        single_asset_reports = sub_location_data.get("asset_data")
        for_loop_count=0
        try:
            asset_health_tables = parseAssetHealthTrend(single_asset_reports)
        except:
            asset_health_tables = None
            # pass

        
        for single_asset_report in single_asset_reports:
            healthFlag=single_asset_report.get("healthFlag")
            chapter_name=single_asset_report.get("location_name")




            chapter_index_name = "chapter_index_name"+str(cout)
            para1 = Paragraph('<a name="{}"></a>{}'.format(chapter_index_name,  '<a href="#{}">{}</a>'.format(chapter_index_name, chapter_name)), style=styles['Heading1'])
            
            para = Paragraph("     "+healthFlagToColorImage[healthFlag]+single_asset_report.get("asset_name"), style=styles['Heading2'])

            toc.addEntry(1,"     "+healthFlagToColorImage[healthFlag]+single_asset_report.get("asset_name"), cout)
            if for_loop_count ==0:
                Story.append(para1)
                # Story.append(PageBreak())

                barGraphHeading1 = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Asset Fault Summary Data") 
                secondBarGraph = parseAssetFaultBarGraph(sub_location_data.get("sub_location_asset_fault_summary_data"),400,200)
                Story.append(barGraphHeading1)
                verticalSpacer = Spacer(1, 0.5 * inch)
                Story.append(secondBarGraph)
                Story.append(verticalSpacer)
                Story.append(verticalSpacer)                
                barGraphHeading2 = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Asset Condition Summary Data") 
                secondBarGraph1 = parseAssetConditionBarGraph(sub_location_data.get("sub_location_asset_condition_summary_data"),400,200)
                Story.append(barGraphHeading2)
                Story.append(secondBarGraph1)
                Story.append(verticalSpacer) 

                if asset_health_tables != None:
                    # Story.append(verticalSpacer)
                    barGraphHeading3 = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Equipment Health Trend") 
                    Story.append(barGraphHeading3)
                    # Story.append(Spacer(1,  inch))
                    Story.extend(asset_health_tables)
                    # Story.append(verticalSpacer)
                    # Story.append(verticalSpacer)
                    Story.append(PageBreak())
                else:
                    barGraphHeading3 = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Equipment Health Trend") 
                    Story.append(barGraphHeading3)
                    errorMessage = getErrorMessage(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Trend Not Found") 
                    Story.append(errorMessage)
                    Story.append(PageBreak())
                    
                


            # Story.append(para1)


            Story.append(para)
     

            cout = cout + 1
            for_loop_count=for_loop_count+1


            assetTables = parseAssetDetailLocation(single_asset_report, country_tz) 
            Story.append(Spacer(1, 0.3 * inch))
            Story.extend(assetTables)
            
            Story.append(PageBreak())




    # verticalSpacer = Spacer(1, 0.5 * inch)
    # Story.append(verticalSpacer)
    # # ////////////////// attachments //////////////////
    # attachmentsHeading = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Attachments")  # heading of the section
    # Story.append(attachmentsHeading)
    # Story.append(Spacer(1,0.1*inch))
    # attachments = parseAttachments(json_data)
    # Story.extend(attachments)

    # verticalSpacer = Spacer(1,0.5*inch)
    # Story.append(verticalSpacer)

    # # ////////////////// Observations //////////////////
    # observationHeading = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Observations")  # heading of the section
    # Story.append(observationHeading)
    # Story.append(Spacer(1,0.3*inch))
    # observations = parseObservations(json_data)
    # Story.append(observations)

    # verticalSpacer = Spacer(1,0.5*inch)
    # Story.append(verticalSpacer)

    # # ////////////////// Recommendations //////////////////
    # recommendationsHeading = sectionHeading(width=PAGE_WIDTH-inch, height=0.3*inch, text_color="#000069", text="Recommendations")  # heading of the section
    # Story.append(recommendationsHeading)
    # Story.append(Spacer(1,0.3*inch))
    # recommendations = parseRecommendations(json_data)
    # Story.append(recommendations)

    doc.multiBuild(Story, onLaterPages=myLaterPages)

    return response


# except:
# return Response({'message':'Something is wrong with the data. Please contact admin'}, status=status.HTTP_404_NOT_FOUND)
