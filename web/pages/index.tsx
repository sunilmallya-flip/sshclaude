import Link from 'next/link';

export default function Home() {
  return (
    <main style={{ padding: 20 }}>
      <h1>sshclaude Console</h1>
      <ul>
        <li><Link href="/login-history">Login History</Link></li>
        <li><Link href="/rotate-key">Rotate Key</Link></li>
        <li><Link href="/delete-service">Delete Service</Link></li>
      </ul>
    </main>
  );
}
