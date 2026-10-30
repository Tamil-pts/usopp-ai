# e-design drawing review — 4.99.0

The main sidebar now includes **e-design**, separate from MatchView's two-drawing comparison. This workspace reviews one uploaded circuit PDF without editing its original content.

## Using the workspace

1. Open **e-design** and upload a circuit PDF (up to 75 MB / 150 pages).
2. Select a page, then **Modify**, **Add**, **Remove** or **Comment**. Drag over the drawing to select an area. The shape menu provides a revision cloud, rectangle or arrow; Comment places a note pin.
3. Enter the correction in the right-hand panel and choose **Save correction**. Red marks removals, green additions and amber modifications. Select a saved markup to move it; drag its corner handle to resize, then save. Resolving a correction changes its status and draws its outline dashed.
4. The comments panel groups corrections by page. Filter by current/all pages, correction type, open/resolved status, comment text or author. Selecting a comment opens its page and location. Hide the panel using its close control, or unpin it to float over the drawing. Pinning preference uses the existing account settings store.
5. Use **Share** to grant an enabled account view-only or reviewing access and copy its signed-in review link. A reviewer can create corrections and edit/delete their own corrections. Owners and Admin can manage the review and its corrections. A view-only user cannot change markups. Removing access denies later review, original, image and export requests.
6. **Export** downloads an annotated PDF with a page-linked correction appendix, a Word correction list or CSV. The original PDF can be downloaded separately. Sharing does not send an email or message automatically.

## Storage and integration

Each upload has a generated `edesign_<uuid>` workspace under the existing work directory. `source.pdf` is immutable, `review.json` stores source identity/page geometry, and `review.sqlite3` stores corrections, participants and an audit history of edits/deletions/sharing. Markup coordinates are normalized against the displayed PDF crop and rotation. PDF export maps them back to PDF coordinates; tests cover a cropped, 90-degree-rotated drawing. Export files are unique per request and cleaned after the response.

The authenticated `/api/e-design` router supports listing/uploading reviews, original/preview access, mark creation/update/deletion, sharing and PDF/DOCX/CSV exports. Changes use optimistic versions, rejecting stale updates/deletions with HTTP 409. Access is checked on every request. Shared reviewers cannot edit other authors' comments or grant access. Account roles are unchanged. Validation error logging omits comment contents.

`#e-design/<review-id>` opens a shared review after sign-in. Saved reviews can be reopened from the drawing selector or review list. Frontend drafts remain when switching workspace sections; abandoning an unsaved correction requires confirmation. Markups do not become electrical-design approvals or alter WorkHub project status.

## Verification

- **34 targeted tests passed**: e-design, circuit accuracy/comparison and comparison-report selection.
- New API tests invoke the actual router for upload, previews, save/edit/delete, stale-version conflicts, audit preservation, immutable originals, owner isolation, viewer/reviewer permissions, revocation and all exports.
- PDF rendering verifies that exported markup positions match the displayed crop/rotation.
- All three production interfaces built successfully. UI/API run **4.99.0**; health exposes `eDesignReview=true`.
- Live browser verification used the actual 18-page `4C9935069 - 21-08-26.pdf`: cloud drawing, movement/resizing, add/remove corrections, resolution, comments by page, hide/pin, sharing controls, PDF/Word/CSV downloads, reload/deep link and a 390px viewport. No browser exceptions. Temporary test review, its ownership record and temporary authentication session were removed afterward.
- Artifacts: `.build/edesign/verification.json`, `workspace.png`, `mobile.png`, and PDF/Word/CSV exports.
- Python v1.71 packet validation and the existing PLC comparison engine remain unchanged.

## Scope

Markups are engineering review instructions. This is a PDF annotation workspace, not an electrical CAD editor: moving a markup does not move a circuit component or wire in the source design. Word export contains the page-grouped correction list. Comments update on save/refresh; simultaneous conflicting edits are rejected rather than silently overwritten. Threaded replies, live presence and CAD editing are not part of this addition.
