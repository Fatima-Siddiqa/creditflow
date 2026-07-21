import io


def test_upload_image_sets_content_image_url(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    headers = auth_headers()
    created = client.post("/content", json={"body": "needs an image"}, headers=headers).json()
    print("CREATED:", created)   # add this

    fake_file = io.BytesIO(b"fake image bytes")
    resp = client.post(
        f"/content/{created['id']}/image",
        files={"file": ("test.jpg", fake_file, "image/jpeg")},
        headers=headers,
    )
    print(resp.status_code, resp.json())   # add this
    assert resp.status_code == 200
    assert resp.json()["image_url"].endswith("test.jpg")


def test_upload_image_404_for_other_account(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.upload_dir", str(tmp_path))
    created = client.post("/content", json={"body": "x"}, headers=auth_headers(account_id="acc_a")).json()

    resp = client.post(
        f"/content/{created['id']}/image",
        files={"file": ("test.jpg", io.BytesIO(b"data"), "image/jpeg")},
        headers=auth_headers(account_id="acc_b"),
    )
    assert resp.status_code == 404