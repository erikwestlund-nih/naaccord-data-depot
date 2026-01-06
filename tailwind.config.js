/** @type {import('tailwindcss').Config} */
module.exports = {
  // Note: In Tailwind v4, content scanning is done via @source in CSS
  // See resources/css/app.css for @source directives
  theme: {
    extend: {
      fontSize: {
          'sm-plus': ['0.9375rem', '1.375rem'],
          'xs-plus': ['0.8125rem', '1.125rem']
      },
    },
  },
  plugins: [],
}