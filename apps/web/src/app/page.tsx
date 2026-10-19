import { Footer } from "@/components/Footer";
import { Hero } from "@/components/Hero";
import { HowItWorks } from "@/components/HowItWorks";
import { EvidenceSection } from "@/components/EvidenceSection";
import { Limits } from "@/components/Limits";
import { Metrics } from "@/components/Metrics";
import { Nav } from "@/components/Nav";
import { PrivacySection } from "@/components/PrivacySection";
import { Protector } from "@/components/Protector";

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <PrivacySection />
        <EvidenceSection />
        <Protector />
        <HowItWorks />
        <Metrics />
        <Limits />
      </main>
      <Footer />
    </>
  );
}
