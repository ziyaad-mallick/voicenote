import './globals.css';

export const metadata = {
  title: 'voicenote — evaluation harness',
  description:
    'An explorable record of the voicenote eval harness and the reminder-scheduling bug its datetime metric found.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        style={{
          fontFamily:
            "'IBM Plex Sans', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif",
        }}
      >
        {children}
      </body>
    </html>
  );
}
