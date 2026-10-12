# 0009. ORB keypoints verify media matches geometrically

- Status: Accepted
- Date: 2026-10-12

## Context
The first eval run on real reposts (2026-10-11) found only 2 of 9 recycled posts whose original was in the archive. The misses were not exotic: a TikTok repost with blurred side bars and the top and bottom cut off, a screenshot of a Facebook video player, a news template wrapped around the clip, a different crop of the same frame. pHash compares the whole picture, so any re-framing breaks it, and unrelated news clips already reached pHash 12 to 16, so its limit could not be loosened. SigLIP put the true originals at cosine 0.77 to 0.94, the same range as unrelated clips of similar rivers.

## Options considered
- **Loosen the pHash limit or add a cosine band.** Admits the unrelated clips that already sit at 12 to 16 and at cosine 0.91.
- **Find the footage rectangle inside the frame (gradient-based content box) and hash that.** Tried: the crops were mostly right, but recall did not move, because reposts also cut the original's top and bottom, and pHash needs the same framing.
- **Local features with geometric verification (ORB plus RANSAC).** Matches keypoints and keeps only those consistent with one shift, scale and rotation, so it finds footage inside crops, bars, captions and screenshots.

## Decision
Store ORB keypoints and descriptors (1000 per frame, at 640 px) with each archive frame, and verify every candidate found by pHash or SigLIP with ORB plus RANSAC. A hit with at least 30 inliers is strong. On the eval set the reposts ORB found scored 68 to 438 inliers, one more (h003) scored 24 but is caught by pHash 10, and unrelated clips scored at most 23; recycled recall went from 2 to 6 of 9 with no false strong hits.

## Consequences
- Adds `opencv-python-headless` (CPU only), and about 40 KB of payload per archive frame.
- Matching costs about a second more per post: up to two ORB comparisons per candidate frame (the post frame and its mirror, since ORB is not mirror-invariant).
- The 30-inlier limit sits just above the worst unrelated clip (23) and below a true repost at 24, so it rests on few pairs; it is re-checked on every eval run.
- A different shot of the same scene is still not a match, which is correct: that needs a checker.
