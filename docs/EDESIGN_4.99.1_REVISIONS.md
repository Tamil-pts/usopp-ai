# e-design review: editable PDF and comment revisions

The review workspace supports undo and redo for draft and saved changes. Select a shape to edit its nearby comment or open its properties. Saving, resolving, reopening, restoring or deleting a comment records a revision; restoring creates a new revision and does not erase earlier history. Shared reviewers can edit comments; view-only members cannot.

Export **Review PDF (editable comments)** to share outside uSOPp.ai. The PDF contains standard editable annotations and an attached review record. A recipient needs a PDF editor that supports annotations and saves them in the PDF. Printing or flattening the file destroys editable annotations. To merge their feedback into the original workspace, choose **Import feedback PDF** on that review; alternatively upload the file as a separate review. Import checks the review identity and source drawing and reports conflicts instead of silently overwriting newer work. The author reported by an external PDF is not verified. PDF readers differ in their support for annotation types, replies and attachments.

The original drawing remains unchanged. Export **PDF correction report**, Word or CSV for a report. Embedded full history has an 8 MB limit and export reports an error if exceeded; the server retains the complete history. Existing saved reviews are migrated when opened.
