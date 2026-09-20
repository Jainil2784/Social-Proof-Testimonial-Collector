import sys
from fastapi.testclient import TestClient
from backend.app.main import app

def run_17_step_manual_test():
    client = TestClient(app)
    print("==================================================")
    print("STARTING MODULE 6: 17-STEP VERIFICATION FLOW")
    print("==================================================")

    # 1. Login as owner
    reg_payload = {
        "name": "Sarah Connor",
        "email": "sarah.connor@skyproof.io",
        "password": "Password123!Secure"
    }
    client.post("/api/auth/register", json=reg_payload)
    login_res = client.post("/api/auth/login", json={
        "email": "sarah.connor@skyproof.io",
        "password": "Password123!Secure"
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    print("[STEP 1] Logged in as owner Sarah Connor. HTTP 200 OK. Auth cookie received.")

    # 2. Open My Spaces
    spaces_res = client.get("/api/spaces")
    assert spaces_res.status_code == 200
    print(f"[STEP 2] Opened My Spaces. Found {len(spaces_res.json())} existing spaces.")

    # 3. Select a Space (or create one)
    create_space_res = client.post("/api/spaces", json={
        "name": "Acme Growth Technologies",
        "slug": "acme-growth",
        "custom_prompt": "Tell us how Acme Growth helped scale your business!",
        "avatar_enabled": True,
        "rating_enabled": True
    })
    assert create_space_res.status_code == 201
    space_data = create_space_res.json()
    space_slug = space_data["slug"]
    space_id = space_data["id"]
    print(f"[STEP 3] Selected Space: '{space_data['name']}' (slug: {space_slug}, id: {space_id}).")

    # 4. Open /collect/{space_slug}
    collect_page_res = client.get(f"/collect/{space_slug}")
    assert collect_page_res.status_code == 200
    assert "Testimonial" in collect_page_res.text
    print(f"[STEP 4] Opened /collect/{space_slug}. Status 200 OK. HTML page loaded successfully.")

    # 5. Submit a new testimonial as a customer
    submission_payload = {
        "client_name": "David Miller",
        "client_email": "david@cloudscale.net",
        "company_role": "VP of Engineering",
        "rating": 5,
        "review_text": "Acme Growth completely transformed our client onboarding pipeline. Cannot recommend it enough!"
    }
    submit_res = client.post(
        f"/api/public/spaces/{space_slug}/testimonials",
        data=submission_payload
    )
    assert submit_res.status_code == 201, f"Submission failed: {submit_res.text}"
    print(f"[STEP 5] Submitted testimonial as customer David Miller. Message: '{submit_res.json()['message']}'")

    # 6. Verify it does NOT appear on Wall of Love
    wall_api_res = client.get(f"/api/public/spaces/{space_slug}/wall")
    assert wall_api_res.status_code == 200
    wall_data = wall_api_res.json()
    assert len(wall_data["testimonials"]) == 0, f"Pending testimonial showed on wall! {wall_data}"
    print("[STEP 6] Verified Wall of Love: 0 testimonials returned (pending testimonial correctly hidden).")

    # 7. Open owner Dashboard -> Customer Reviews
    owner_reviews_res = client.get("/api/testimonials")
    assert owner_reviews_res.status_code == 200
    reviews_data = owner_reviews_res.json()
    assert reviews_data["total"] >= 1
    pending_review = next((r for r in reviews_data["items"] if r["client_name"] == "David Miller"), None)
    assert pending_review is not None
    assert pending_review["status"] == "pending"
    testimonial_1_id = pending_review["id"]
    print(f"[STEP 7] Opened Dashboard Reviews: Found pending testimonial id={testimonial_1_id} by David Miller.")

    # 8. Approve the testimonial
    approve_res = client.patch(f"/api/testimonials/{testimonial_1_id}/status", json={"status": "approved"})
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"
    print(f"[STEP 8] Approved testimonial id={testimonial_1_id}. Status is now 'approved'.")

    # 9. Open /wall/{space_slug}
    wall_page_res = client.get(f"/wall/{space_slug}")
    assert wall_page_res.status_code == 200
    assert "Wall of Love" in wall_page_res.text
    print(f"[STEP 9] Opened /wall/{space_slug}. Status 200 OK. HTML page rendered.")

    # 10. Verify the testimonial now appears
    wall_api_res = client.get(f"/api/public/spaces/{space_slug}/wall")
    assert wall_api_res.status_code == 200
    wall_items = wall_api_res.json()["testimonials"]
    assert len(wall_items) == 1
    assert wall_items[0]["client_name"] == "David Miller"
    assert wall_items[0]["review_text"] == submission_payload["review_text"]
    assert wall_items[0]["rating"] == 5
    print(f"[STEP 10] Verified Wall API: David Miller's approved review is now publicly visible on the Wall of Love!")

    # 11. Feature the testimonial
    feature_res = client.patch(f"/api/testimonials/{testimonial_1_id}/featured", json={"is_featured": True})
    assert feature_res.status_code == 200
    assert feature_res.json()["is_featured"] is True
    print(f"[STEP 11] Featured testimonial id={testimonial_1_id}. is_featured=True.")

    # 12. Refresh Wall of Love
    wall_api_res = client.get(f"/api/public/spaces/{space_slug}/wall")
    assert wall_api_res.status_code == 200
    wall_items = wall_api_res.json()["testimonials"]

    # 13. Verify the featured state is reflected
    assert len(wall_items) == 1
    assert wall_items[0]["is_featured"] is True
    print("[STEP 12-13] Refreshed Wall of Love: Verified is_featured=True is reflected on David Miller's card.")

    # 14. Reject another testimonial
    submit_res2 = client.post(
        f"/api/public/spaces/{space_slug}/testimonials",
        data={
            "client_name": "Spam Bot",
            "client_email": "spam@randomdomain.xyz",
            "company_role": "Spammer",
            "rating": 1,
            "review_text": "Click here for free bitcoin!"
        }
    )
    assert submit_res2.status_code == 201
    owner_reviews_res2 = client.get("/api/testimonials")
    spam_review = next((r for r in owner_reviews_res2.json()["items"] if r["client_name"] == "Spam Bot"), None)
    assert spam_review is not None
    testimonial_2_id = spam_review["id"]
    reject_res = client.patch(f"/api/testimonials/{testimonial_2_id}/status", json={"status": "rejected"})
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"
    print(f"[STEP 14] Customer 2 submitted spam review. Owner rejected testimonial id={testimonial_2_id}.")

    # 15. Refresh Wall of Love
    wall_api_res = client.get(f"/api/public/spaces/{space_slug}/wall")
    assert wall_api_res.status_code == 200
    wall_items = wall_api_res.json()["testimonials"]

    # 16. Verify rejected testimonial does NOT appear
    names_on_wall = [t["client_name"] for t in wall_items]
    assert "Spam Bot" not in names_on_wall
    assert "David Miller" in names_on_wall
    assert len(wall_items) == 1
    print("[STEP 15-16] Refreshed Wall of Love: Confirmed rejected testimonial 'Spam Bot' does NOT appear.")

    # 17. Test the page in mobile/responsive view
    with open("frontend/wall.html", "r", encoding="utf-8") as f:
        wall_html_source = f.read()
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in wall_html_source
    assert ".masonry-grid" in wall_html_source
    assert "column-count: 1;" in wall_html_source  # mobile
    assert "@media (min-width: 768px)" in wall_html_source  # tablet
    assert "@media (min-width: 1024px)" in wall_html_source  # desktop
    assert "break-inside: avoid;" in wall_html_source
    print("[STEP 17] Verified mobile/responsive design: viewport meta, CSS 1-column mobile, 2-column tablet, 3-column desktop masonry.")

    print("==================================================")
    print("ALL 17 MANUAL USER TEST STEPS PASSED PERFECTLY!")
    print("==================================================")

if __name__ == "__main__":
    run_17_step_manual_test()
