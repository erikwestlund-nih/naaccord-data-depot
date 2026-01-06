"""
Security tests for Cross-Site Scripting (XSS) prevention.
Tests that user input is properly escaped in templates.
"""
from django.template import Template, Context
from depot.tests.base_security import SecurityTestCase


class XSSPreventionTest(SecurityTestCase):
    """Test that XSS attacks are prevented in templates."""

    def test_template_auto_escaping_enabled(self):
        """Django templates should have auto-escaping enabled by default."""
        template = Template("{{ user_input }}")
        malicious_input = "<script>alert('XSS')</script>"

        output = template.render(Context({'user_input': malicious_input}))

        # Should be escaped
        self.assertIn('&lt;script&gt;', output,
            "Script tags should be escaped")
        self.assertNotIn('<script>', output,
            "Raw script tags should not appear")

    def test_html_tags_escaped_in_output(self):
        """HTML tags in user input should be escaped."""
        template = Template("{{ name }}")

        malicious_names = [
            "<img src=x onerror=alert('XSS')>",
            "<iframe src='javascript:alert(1)'>",
            "<svg onload=alert('XSS')>",
        ]

        for malicious_name in malicious_names:
            output = template.render(Context({'name': malicious_name}))

            # Should be escaped
            self.assertIn('&lt;', output,
                f"HTML should be escaped: {malicious_name}")
            self.assertNotIn('<img', output.lower())
            self.assertNotIn('<iframe', output.lower())
            self.assertNotIn('<svg', output.lower())

    def test_javascript_variable_escaping(self):
        """JavaScript variables with user input should be properly escaped."""
        template = Template("""
            <script>
                var userName = "{{ user_name|escapejs }}";
            </script>
        """)

        malicious_name = '\"; alert(\"XSS\"); \"'
        output = template.render(Context({'user_name': malicious_name}))

        # Should be escaped for JavaScript context
        self.assertNotIn('alert("XSS")', output,
            "JavaScript injection should be escaped")

    def test_event_handlers_escaped(self):
        """Event handler attributes should be escaped."""
        template = Template('<div title="{{ title }}">Content</div>')

        malicious_title = '" onmouseover="alert(\'XSS\')"'
        output = template.render(Context({'title': malicious_title}))

        # Quotes should be escaped, preventing attribute injection
        self.assertIn('&quot;', output,
            "Quotes should be escaped to prevent attribute injection")

        # The escaped output should not break out of the attribute
        # The onmouseover text is escaped, not executed
        self.assertIn('title="&quot;', output,
            "Title attribute should contain escaped quote")

    def test_attribute_value_escaping(self):
        """Attribute values should be properly escaped."""
        template = Template('<input type="text" value="{{ value }}">')

        malicious_values = [
            '" onload="alert(\'XSS\')"',
            '" ><script>alert("XSS")</script><input value="',
        ]

        for malicious_value in malicious_values:
            output = template.render(Context({'value': malicious_value}))

            # Quotes and tags should be escaped
            self.assertIn('&quot;', output,
                f"Quotes should be escaped: {malicious_value}")

            # The value attribute should not be broken out of
            self.assertIn('value="&quot;', output,
                f"Value attribute should contain escaped content")
