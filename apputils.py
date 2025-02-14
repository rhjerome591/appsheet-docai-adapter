import base64
import logging
import pprint
import os
import io
import datetime

from proto import fields
import google.auth
from googleapiclient.http import MediaIoBaseDownload
from google.cloud import documentai_v1 as documentai
git_pat = "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"
# import google.auth.transport.requests
from google.auth.transport.requests import AuthorizedSession
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build

creds, project = google.auth.default(
    scopes=[
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
location = os.getenv('GCP_DOCAI_REGION')
processor_id = os.getenv('GCP_DOCAI_PROCESSOR_ID')



def getFile(topic, image):
    imageResult = ""

    if "_Files/" in image:
        logging.error("Retrieving Google Drive image: " + image)

        a = datetime.datetime.now()
        imageResult = getFileFromDrive(image.split("/")[-1])
        b = datetime.datetime.now()
        c = b - a

        logging.error(
            "{s} ms to get image from google drive.".format(s=c.total_seconds() * 1000)
        )
    elif image.startswith("data:image/png;base64,"):
        imageResult = image.replace("data:image/png;base64,", "")
        imageResult = imageResult.split("#filename=", 1)[0]
    elif image.startswith("data:image/jpeg;base64,"):
        imageResult = image.replace("data:image/jpeg;base64,", "")
        imageResult = imageResult.split("#filename=", 1)[0]
    elif image.startswith("data:image/jpg;base64,"):
        imageResult = image.replace("data:image/jpg;base64,", "")
        imageResult = imageResult.split("#filename=", 1)[0]

    return imageResult


def getFileFromDrive(name):
    service = build("drive", "v3", credentials=creds)
    page_token = None

    response = (
        service.files()
        .list(
            q="name='" + name + "'",
            spaces="drive",
            fields="nextPageToken, files(id, name, thumbnailLink)",
            pageToken=page_token,
        )
        .execute()
    )

    files = response.get("files", [])

    if len(files) > 0:
        for file in response.get("files", []):
            # Process change
            print("Found file: " + file.get("name") + " and id: " + file.get("id"))
            request = service.files().get_media(fileId=file.get("id"))
            # fh = io.BytesIO()
            fh = io.FileIO("image.png", "wb")
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print("Download " + str(int(status.progress() * 100)))

            # output["formThumbnail"] = file["thumbnailLink"]
            break

        with open("image.png", "rb") as imageFile:
            encoded_string = base64.b64encode(imageFile.read()).decode("utf-8")
    else:
        encoded_string = "error"

    return encoded_string

# Method to call the Document AI API and get the form processing results
def callDocAI(documentPath: str):

  output = {
    "text": "",
    "formFields": "",
    "entities": "",
    "image": "",
    "totalFields": 0,
    "filledFields": 0
  }

  # creds, project_id = google.auth.default(scopes=SCOPES)
  # creds = service_account.Credentials.default(scopes=SCOPES)

  service = build('drive', 'v3', credentials=creds)
  page_token = None

  response = service.files().list(q="name='" + documentPath.split("/")[-1] + "'",
                                        spaces='drive',
                                        fields='nextPageToken, files(id, name, thumbnailLink)',
                                        pageToken=page_token).execute()

  for file in response.get('files', []):
    # Process change
    print("Found file: " + file.get('name') + " and id: " + file.get('id'))
    request = service.files().get_media(fileId=file.get('id'))
    # fh = io.BytesIO()
    fh = io.FileIO('tempdoc.pdf', 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
      status, done = downloader.next_chunk()
      print("Download " + str(int(status.progress() * 100)))

    if "thumbnailLink" in file:
        output["image"] = file["thumbnailLink"]
    
    break

  opts = {"api_endpoint": location + "-documentai.googleapis.com"}

  client = documentai.DocumentProcessorServiceClient(client_options=opts)
  name = f"projects/{project}/locations/{location}/processors/{processor_id}"

  with open("tempdoc.pdf", "rb") as image:
      image_content = image.read()

  mime = "application/pdf"
  if documentPath.endswith(".png"):
    mime = "image/png"

  document = {"content": image_content, "mime_type": mime}

  # Configure the process request
  request = {"name": name, "raw_document": document}

  result = client.process_document(request=request)
  document = result.document

  document_pages = document.pages

  output["text"] = document.text
  formFields = ""
  entities = ""
  for page in document_pages:
    # if page.page_number == 1:
        #output["formThumbnail"] = "data:image/png;base64," + page.image.content.decode("utf-8")
        # pic = base64.b64encode(page.image.content)
        # output["image"] = pic.decode("utf-8")

    for form_field in page.form_fields:
        fieldLabel = _get_text(form_field.field_name, document).replace("\n", "").replace(":", "").strip()
        fieldValue = _get_text(form_field.field_value, document).replace("\n", "")
        formFields += "\n" + fieldLabel + "=" + fieldValue

        output["totalFields"] = output["totalFields"] + 1
        if fieldValue != "":
            output["filledFields"] = output["filledFields"] + 1

  output["formFields"] = formFields

  for entity in document.entities:
    name = entity.type_
    value = entity.mention_text
    entities += "\n" + name + "=" + value

  output["entities"] = entities

  return output

# Helper function to get text from form fields
def _get_text(el, document):
    """Doc AI identifies form fields by their offsets
    in document text. This function converts offsets
    to text snippets.
    """
    response = ""
    # If a text segment spans several lines, it will
    # be stored in different text segments.
    for segment in el.text_anchor.text_segments:
        start_index = segment.start_index
        end_index = segment.end_index
        response += document.text[start_index:end_index]
    return response

# Helper function to get text from form fields
def get_text(doc_element: dict, document: dict):
    """
    Document AI identifies form fields by their offsets
    in document text. This function converts offsets
    to text snippets.
    """
    response = ""
    # If a text segment spans several lines, it will
    # be stored in different text segments.
    for segment in doc_element.text_anchor.text_segments:
        start_index = (
            int(segment.start_index)
            if segment in doc_element.text_anchor.text_segments
            else 0
        )
        end_index = int(segment.end_index)
        response += document.text[start_index:end_index]
    return response
