"use client";

import { EducationHub } from "../components/EducationHub";
import Navbar from "../components/Navbar";
import Chatbot from "../components/Chatbot";

export default function CoursesPage() {
  return (
    <div className="min-h-screen bg-[#0b0b12] text-white">
      <Navbar />
      <Chatbot currentPage="courses" />
      <div className="pt-24"> {/* Adds space below navbar */}
        <EducationHub />
      </div>
    </div>
  );
}
