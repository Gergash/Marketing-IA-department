package publisher

import "testing"

// TestUserClipReelRoutedToReelsBranch verifica que content_format="user_clip_reel"
// se rutea al mismo branch REELS que "reel" (video_url + media_type=REELS + timeout largo).
func TestUserClipReelRoutedToReelsBranch(t *testing.T) {
	req := PublishRequest{
		ContentFormat: "user_clip_reel",
		VideoURL:      "http://example.com/clip.mp4",
		Copy:          "mi copy",
		AccessToken:   "tok",
	}

	params, timeout := buildMediaParams(req)

	if got := params.Get("video_url"); got != req.VideoURL {
		t.Errorf("video_url = %q, want %q", got, req.VideoURL)
	}
	if got := params.Get("media_type"); got != "REELS" {
		t.Errorf("media_type = %q, want REELS", got)
	}
	if got := params.Get("share_to_feed"); got != "true" {
		t.Errorf("share_to_feed = %q, want true", got)
	}
	if timeout != reelMediaContainerTimeout {
		t.Errorf("containerTimeout = %v, want %v", timeout, reelMediaContainerTimeout)
	}
}

// TestReelStillRoutedToReelsBranch es la regresion: "reel" debe seguir enrutado igual.
func TestReelStillRoutedToReelsBranch(t *testing.T) {
	req := PublishRequest{
		ContentFormat: "reel",
		VideoURL:      "http://example.com/reel.mp4",
		Copy:          "otro copy",
		AccessToken:   "tok",
	}

	params, timeout := buildMediaParams(req)

	if got := params.Get("video_url"); got != req.VideoURL {
		t.Errorf("video_url = %q, want %q", got, req.VideoURL)
	}
	if got := params.Get("media_type"); got != "REELS" {
		t.Errorf("media_type = %q, want REELS", got)
	}
	if got := params.Get("share_to_feed"); got != "true" {
		t.Errorf("share_to_feed = %q, want true", got)
	}
	if timeout != reelMediaContainerTimeout {
		t.Errorf("containerTimeout = %v, want %v", timeout, reelMediaContainerTimeout)
	}
}

// TestStoryAndFeedUnaffected: regresion de los otros dos branches (no video).
func TestStoryAndFeedUnaffected(t *testing.T) {
	story := PublishRequest{ContentFormat: "story", ImageURL: "http://example.com/s.png", AccessToken: "tok"}
	params, timeout := buildMediaParams(story)
	if got := params.Get("media_type"); got != "STORIES" {
		t.Errorf("story media_type = %q, want STORIES", got)
	}
	if timeout != mediaContainerTimeout {
		t.Errorf("story containerTimeout = %v, want %v", timeout, mediaContainerTimeout)
	}

	feed := PublishRequest{ContentFormat: "feed", ImageURL: "http://example.com/f.png", Copy: "c", AccessToken: "tok"}
	params, timeout = buildMediaParams(feed)
	if got := params.Get("image_url"); got != feed.ImageURL {
		t.Errorf("feed image_url = %q, want %q", got, feed.ImageURL)
	}
	if timeout != mediaContainerTimeout {
		t.Errorf("feed containerTimeout = %v, want %v", timeout, mediaContainerTimeout)
	}
}
