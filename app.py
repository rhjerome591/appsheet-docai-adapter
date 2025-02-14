import pprint
import json
import logging
import requests
import io
import os
import os.path

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import google.auth

from flask import Flask, request, jsonify

from apputils import getFile, callDocAI

# Flask App Initialization
app = Flask(__name__)
topic = "documents"

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(
        cred,
        {
            "projectId": cred.project_id,
        },
    )

db = firestore.client()


# Routes
@app.route(f"/{topic}", methods=["GET"])
@app.route(f"/{topic}/<string:doc_id>", methods=["GET"])
def get_documents(doc_id=None):
    """Returns all documents or a specific document by ID."""
    new_result = {}

    if doc_id is None:
        forms_ref = db.collection(topic)
        forms = forms_ref.stream()
        new_result = {topic: [form.to_dict() for form in forms]}
    else:
        doc_ref = db.collection(topic).document(doc_id)
        doc = doc_ref.get()
        new_result = doc.to_dict()

    if new_result:
        return jsonify(new_result)
    else:
        return jsonify({"error": "Not found"}), 404


@app.route(f"/{topic}", methods=["POST"])
def post_document():
    """Posts a new object to be stored."""
    data = request.get_json()
    documentPath = data.get("file", "")

    logging.error("Calling DocAI with file path: " + documentPath)

    result = callDocAI(documentPath)
    data.update(
        {
            "text": result["text"],
            "formFields": result["formFields"],
            "image": result["image"],
            "totalFields": result["totalFields"],
            "filledFields": result["filledFields"],
            "entities": result["entities"],
        }
    )

    db.collection(topic).document(data["id"]).set(data)
    return jsonify(data)


@app.route(f"/{topic}", methods=["PUT"])
def put_document():
    """Updates an existing object."""
    data = request.get_json()
    logging.info(json.dumps(data))

    db.collection(topic).document(data["id"]).set(data)

    pprint.pprint(data)
    return jsonify(data)


@app.route(f"/{topic}/<string:doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    """Deletes an object by ID."""
    if doc_id:
        db.collection(topic).document(doc_id).delete()

    return jsonify({"message": "Deleted successfully"}), 200


@app.route("/", methods=["GET"])
def get_openapi_spec():
    """Returns the OpenAPI spec, replacing the server URL dynamically."""
    try:
        with open("apispec.yaml", "r") as f:
            spec = f.read()
            server_url = request.host_url.replace("http://", "https://")
            spec = spec.replace("SERVER_URL", server_url)
        return spec, 200, {"Content-Type": "text/plain;charset=UTF-8"}
    except FileNotFoundError:
        return jsonify({"error": "API spec file not found"}), 404


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
