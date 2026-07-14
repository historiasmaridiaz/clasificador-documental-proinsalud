import unittest

from core.ui_theme import build_theme_css


class ThemeVisibilityTests(unittest.TestCase):
    def test_dark_theme_styles_all_problem_controls_with_high_contrast(self):
        css = build_theme_css(dark_mode=True, focus_mode=False)
        self.assertIn('[data-testid="stPopover"] > button', css)
        self.assertIn('[data-testid="stSelectbox"] div[data-baseweb="select"] > div', css)
        self.assertIn('button[data-testid^="stBaseButton-"]', css)
        self.assertIn('background:var(--pro-control)!important', css)
        self.assertIn('color:#FFFFFF!important', css)

    def test_data_editor_overlay_keeps_readable_contrast_in_dark_mode(self):
        css = build_theme_css(dark_mode=True, focus_mode=False)
        self.assertIn('--gdg-bg-cell:#F7FAFD!important', css)
        self.assertIn('--gdg-text-dark:#12375F!important', css)
        self.assertIn('.gdg-style .glide-select', css)
        self.assertIn('color-scheme:light!important', css)

    def test_focus_mode_hides_navigation(self):
        css = build_theme_css(dark_mode=False, focus_mode=True)
        self.assertIn('[data-testid="stSidebar"]', css)
        self.assertIn('display:none!important', css)


if __name__ == "__main__":
    unittest.main()
