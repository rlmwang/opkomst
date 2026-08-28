# Images

An organiser can put one image on the thing they make. It shows on the
public page, on the agenda card and in the link preview.

Images are stored outside the database and served from this app's own
domain, never from wherever they physically live. That indirection is
the point: the storage host can change without breaking a link that is
already in somebody's inbox.

Uploads are re-encoded rather than passed through: resized, cropped to
a fixed aspect, flattened onto white and written as JPEG. What arrives
is not what is served, so an image cannot smuggle anything.

An image is deleted when the thing it belongs to is deleted, and a
daily reaper removes the images of entities that have been archived
longer than the grace period. `services/image_reaper.py` is that sweep.
