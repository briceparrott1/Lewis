import io

from docx import Document

from lewis_api.profile.resume import extract_resume_text


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_docx():
    data = _docx_bytes("Forward Deployed Engineer, Python, SQL")
    text = extract_resume_text("resume.docx", data)
    assert "Forward Deployed Engineer" in text


async def _signup(client, email="p@e.com"):
    await client.post("/api/auth/signup", json={"email": email, "password": "hunter2"})


async def test_upload_resume_and_get_profile(client):
    await _signup(client)
    data = _docx_bytes("Python engineer")
    resp = await client.post(
        "/api/profile/resume",
        files={
            "file": (
                "r.docx",
                data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp.status_code == 200
    assert "Python engineer" in resp.json()["resume_text"]

    prof = await client.get("/api/profile")
    assert "Python engineer" in prof.json()["resume_text"]


async def test_put_prefs(client):
    await _signup(client, "pref@e.com")
    resp = await client.put("/api/profile/prefs", json={"raw_prefs_text": "FDE in SF"})
    assert resp.status_code == 200
    prof = await client.get("/api/profile")
    assert prof.json()["raw_prefs_text"] == "FDE in SF"


async def test_put_name(client):
    await _signup(client, "name@e.com")
    resp = await client.put("/api/profile/name", json={"name": "Brice"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Brice"
    prof = await client.get("/api/profile")
    assert prof.json()["name"] == "Brice"
