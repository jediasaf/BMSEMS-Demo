import { redirect } from 'next/navigation';

/**
 * No landing page. This is an operational application, so opening it puts you
 * in the building operator's workspace — not in front of a hero banner.
 */
export default function Home() {
  redirect('/bms');
}
