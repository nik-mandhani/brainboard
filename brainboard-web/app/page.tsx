"use client";

import { useEffect, useMemo, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { CheckCircle2, Circle, Trash2 } from "lucide-react";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

type BrainboardItem = {
  id: string;
  title: string;
  summary: string;
  category: string;
  source_type: string;
  source_name: string;
  url: string | null;
  original_message: string;
  created_at: string;
  is_read: boolean;
};

export default function Home() {
  const [items, setItems] = useState<BrainboardItem[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("Unread");
  const [loading, setLoading] = useState(true);
  const [dark, setDark] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});

  async function fetchItems(showLoading = false) {
    if (showLoading) setLoading(true);

    const { data, error } = await supabase
      .from("brainboard_items")
      .select("*")
      .order("created_at", { ascending: false });

    if (!error) setItems(data || []);
    if (showLoading) setLoading(false);
  }

  async function deleteItem(id: string) {
    const confirmDelete = window.confirm("Delete this item?");
    if (!confirmDelete) return;

    const { error } = await supabase
      .from("brainboard_items")
      .delete()
      .eq("id", id);

    if (!error) {
      setItems((prev) => prev.filter((item) => item.id !== id));
    } else {
      console.error("Delete error:", error);
      alert("Could not delete item");
    }
  }

  async function toggleRead(item: BrainboardItem) {
    const newValue = !item.is_read;

    setItems((prev) =>
      prev.map((x) => (x.id === item.id ? { ...x, is_read: newValue } : x))
    );

    const { error } = await supabase
      .from("brainboard_items")
      .update({ is_read: newValue })
      .eq("id", item.id);

    if (error) {
      console.error("Read update error:", error);
      setItems((prev) =>
        prev.map((x) =>
          x.id === item.id ? { ...x, is_read: item.is_read } : x
        )
      );
    }
  }

  async function markAsRead(item: BrainboardItem) {
    if (item.is_read) return;

    setItems((prev) =>
      prev.map((x) => (x.id === item.id ? { ...x, is_read: true } : x))
    );

    const { error } = await supabase
      .from("brainboard_items")
      .update({ is_read: true })
      .eq("id", item.id);

    if (error) console.error("Mark read error:", error);
  }

  useEffect(() => {
    fetchItems(true);

    const timer = setInterval(() => {
      fetchItems(false);
    }, 5000);

    return () => clearInterval(timer);
  }, []);

  const filters = useMemo(() => {
    const categories = items.map((item) => item.category).filter(Boolean);
    const sources = items.map((item) => item.source_type).filter(Boolean);

    return ["Unread", "Read", ...Array.from(new Set([...categories, ...sources]))];
  }, [items]);

  const filteredItems = items.filter((item) => {
    const q = search.toLowerCase();

    const matchesSearch =
      item.title?.toLowerCase().includes(q) ||
      item.summary?.toLowerCase().includes(q) ||
      item.original_message?.toLowerCase().includes(q);

    const matchesFilter =
      (filter === "Unread" && !item.is_read) ||
      (filter === "Read" && item.is_read) ||
      (filter !== "Unread" &&
        filter !== "Read" &&
        !item.is_read &&
        (item.category === filter || item.source_type === filter));

    return matchesSearch && matchesFilter;
  });

  const bg = dark
    ? "bg-[#071018] text-white"
    : "bg-gradient-to-br from-[#EBF6FB] via-[#DFF2FA] to-[#F8FCFF] text-[#10202B]";

  const card = dark
    ? "bg-[#101B24]/90 border-white/10"
    : "bg-white/85 border-[#B9DCEB]/70 shadow-[0_18px_50px_rgba(36,99,130,0.12)]";

  const readCard = dark
    ? "bg-[#0B1218]/95 border-white/5 opacity-70"
    : "bg-[#D8EAF2]/90 border-[#AACFDD] opacity-75";

  const muted = dark ? "text-slate-400" : "text-slate-500";

  return (
    <main className={`min-h-screen ${bg}`}>
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 sm:px-8 lg:px-12">
        <header className="pb-5 pt-3">
          <nav
            className={`mb-6 flex items-center justify-between rounded-2xl border px-5 py-3 backdrop-blur ${
              dark ? "border-white/10 bg-white/5" : "border-white/70 bg-white/45"
            }`}
          >
            <div className="text-base font-semibold tracking-tight">Brainboard</div>

            <button
              onClick={() => setDark(!dark)}
              className={`rounded-full border px-4 py-2 text-sm transition ${
                dark
                  ? "border-white/15 bg-white text-black"
                  : "border-[#B9DCEB] bg-[#10202B] text-white"
              }`}
            >
              {dark ? "Light" : "Dark"}
            </button>
          </nav>

          <div className="max-w-2xl">
            <h1 className="text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
              Save your ideas
            </h1>

            <p className={`mt-3 text-sm leading-6 ${muted}`}>
              Links, tweets, notes and thoughts organized beautifully.
            </p>
          </div>
        </header>

        <section
          className={`sticky top-0 z-10 -mx-4 border-y px-4 py-5 backdrop-blur-xl sm:-mx-8 sm:px-8 lg:-mx-12 lg:px-12 ${
            dark
              ? "border-white/10 bg-[#071018]/90"
              : "border-[#B9DCEB]/70 bg-[#EBF6FB]/80"
          }`}
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full lg:max-w-md">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
                ⌕
              </span>

              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search Brainboard..."
                className={`w-full rounded-2xl border py-3 pl-10 pr-4 text-sm outline-none transition ${
                  dark
                    ? "border-white/10 bg-white/5 text-white placeholder:text-slate-600 focus:border-sky-300"
                    : "border-[#B9DCEB] bg-white/80 text-[#10202B] placeholder:text-slate-400 focus:border-[#4BA3C7]"
                }`}
              />
            </div>

            <div className="flex gap-2 overflow-x-auto pb-1">
              {filters.map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`whitespace-nowrap rounded-full border px-4 py-2 text-sm transition ${
                    filter === f
                      ? dark
                        ? "border-sky-300 bg-sky-300 text-black"
                        : "border-[#10202B] bg-[#10202B] text-white"
                      : dark
                      ? "border-white/10 bg-white/5 text-slate-300 hover:border-sky-300/50"
                      : "border-[#B9DCEB] bg-white/70 text-slate-700 hover:border-[#4BA3C7]"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="flex-1 py-8">
          {loading ? (
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((item) => (
                <div
                  key={item}
                  className={`h-80 animate-pulse rounded-[2rem] border ${card}`}
                />
              ))}
            </div>
          ) : filteredItems.length === 0 ? (
            <div className={`rounded-[2rem] border p-16 text-center ${card}`}>
              <h2 className="text-xl font-semibold">No items found</h2>
              <p className={`mt-2 text-sm ${muted}`}>
                Try another search or change your filter.
              </p>
            </div>
          ) : (
            <div className="grid auto-rows-fr gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {filteredItems.map((item) => {
                const points = (item.summary || "")
                  .split("\n")
                  .map((p) => p.trim())
                  .filter(Boolean);

                const isExpanded = expandedItems[item.id] === true;
                const visiblePoints = isExpanded ? points : points.slice(0, 3);

                return (
                  <article
                    key={item.id}
                    className={`group flex h-[380px] flex-col rounded-[2rem] border p-6 backdrop-blur transition duration-200 hover:-translate-y-1 ${
                      item.is_read ? readCard : card
                    }`}
                  >
                    <div className="mb-5 flex items-center justify-between gap-3">
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-medium ${
                          dark
                            ? "bg-sky-300/10 text-sky-200"
                            : "bg-[#E6F4FA] text-[#245B72]"
                        }`}
                      >
                        {item.category || "Other"}
                      </span>

                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => toggleRead(item)}
                          className={`flex h-8 w-8 items-center justify-center rounded-full transition ${
                            item.is_read
                              ? dark
                                ? "text-emerald-300 hover:bg-emerald-400/10"
                                : "text-emerald-700 hover:bg-emerald-50"
                              : dark
                              ? "text-slate-400 hover:bg-white/10 hover:text-white"
                              : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          }`}
                          title={item.is_read ? "Mark as unread" : "Mark as read"}
                        >
                          {item.is_read ? (
                            <CheckCircle2 size={17} strokeWidth={2} />
                          ) : (
                            <Circle size={17} strokeWidth={2} />
                          )}
                        </button>

                        <button
                          onClick={() => deleteItem(item.id)}
                          className={`flex h-8 w-8 items-center justify-center rounded-full transition ${
                            dark
                              ? "text-slate-400 hover:bg-red-500/10 hover:text-red-300"
                              : "text-slate-400 hover:bg-red-50 hover:text-red-600"
                          }`}
                          title="Delete"
                        >
                          <Trash2 size={16} strokeWidth={2} />
                        </button>
                      </div>
                    </div>

                    <h2 className="mb-4 text-xl font-semibold leading-snug tracking-[-0.02em]">
                      {item.title}
                    </h2>

                    <div className={`mb-6 max-h-[150px] overflow-y-auto pr-2 space-y-3 text-sm leading-6 ${muted}`}>
                      {visiblePoints.map((point, index) => (
                        <p key={index} className="flex gap-2">
                          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#4BA3C7]" />
                          <span>{point.replace(/^[-•]\s*/, "")}</span>
                        </p>
                      ))}

                      {points.length > 3 && (
                        <button
                          onClick={() =>
                            setExpandedItems((prev) => ({
                              ...prev,
                              [item.id]: !isExpanded,
                            }))
                          }
                          className={`pt-1 text-sm font-medium transition ${
                            dark
                              ? "text-sky-300 hover:text-sky-200"
                              : "text-[#245B72] hover:text-[#10202B]"
                          }`}
                        >
                          {isExpanded ? "Show less" : `Read more +${points.length - 3}`}
                        </button>
                      )}
                    </div>

                    <div
                      className={`mt-auto flex items-center justify-between border-t pt-5 ${
                        dark ? "border-white/10" : "border-[#D7EAF2]"
                      }`}
                    >
                      <span className={`text-xs ${muted}`}>
                        {item.is_read ? "Read" : "Unread"}
                      </span>

                      {item.url ? (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={() => markAsRead(item)}
                          className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                            dark
                              ? "bg-sky-300 text-black hover:bg-sky-200"
                              : "bg-[#10202B] text-white hover:bg-[#245B72]"
                          }`}
                        >
                          Open Link
                        </a>
                      ) : (
                        <span className={`text-sm ${muted}`}>Saved note</span>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <footer
          className={`mt-6 border-t py-8 text-center text-xs ${
            dark ? "border-white/10 text-slate-500" : "border-[#B9DCEB] text-slate-500"
          }`}
        >
          Brainboard · Your personal memory layer from WhatsApp.
        </footer>
      </div>
    </main>
  );
}