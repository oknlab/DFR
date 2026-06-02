import { createApp, computed, onMounted, ref } from 'https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.esm-browser.prod.js'

const icons = {
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Z"/><path d="m9 12 2 2 4-4"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
  eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m2 2 20 20"/><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 4.2A10.8 10.8 0 0 1 12 4c7 0 10 8 10 8a13.2 13.2 0 0 1-2.2 3.3"/><path d="M6.6 6.6C3.5 8.7 2 12 2 12s3 8 10 8c1.4 0 2.7-.3 3.8-.8"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.3L5.8 21 7 14.2 2 9.3l6.9-1L12 2Z"/></svg>',
}

createApp({
  setup() {
    const query = ref('privacy search engine')
    const maxResults = ref(8)
    const hidePromoted = ref(true)
    const strictPrivacy = ref(true)
    const loading = ref(false)
    const error = ref('')
    const results = ref([])
    const sources = ref({ web: [], documents: [], images: [], news: [], social: [] })
    const bangs = ref([])
    const activeTab = ref('web')
    const bangRedirect = ref('')
    const googleProxyUrl = ref('')
    const rankings = ref(JSON.parse(localStorage.getItem('oknlab-rankings') || '{}'))
    const tabs = [{ id: 'web', label: 'Web' }, { id: 'images', label: 'Images' }, { id: 'news', label: 'News' }, { id: 'documents', label: 'Docs' }, { id: 'social', label: 'Social' }]
    const visibleResults = computed(() => activeTab.value === 'web' ? results.value : sources.value?.[activeTab.value] || [])
    const domainOf = (url) => { try { return new URL(url).hostname.replace('www.', '') } catch { return 'unknown source' } }
    const rank = (url, delta) => {
      const domain = domainOf(url)
      rankings.value = { ...rankings.value, [domain]: (rankings.value[domain] || 0) + delta }
      localStorage.setItem('oknlab-rankings', JSON.stringify(rankings.value))
      results.value = [...results.value].sort((a, b) => (rankings.value[domainOf(b.url)] || 0) - (rankings.value[domainOf(a.url)] || 0))
    }
    const loadBangs = async () => { const response = await fetch('/api/bangs'); bangs.value = await response.json() }
    const search = async () => {
      if (!query.value.trim()) return
      loading.value = true; error.value = ''; bangRedirect.value = ''
      try {
        const response = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: query.value, max_results: Number(maxResults.value), hide_promoted: hidePromoted.value, strict_privacy: strictPrivacy.value, rankings: rankings.value }) })
        if (!response.ok) throw new Error(`Search failed (${response.status})`)
        const data = await response.json()
        if (data.bang_redirect) { bangRedirect.value = data.bang_redirect; results.value = []; return }
        results.value = data.results || []
        sources.value = data.sources || { web: [], documents: [], images: [], news: [], social: [] }
        googleProxyUrl.value = data.google_proxy_url
      } catch (err) { error.value = err.message || 'Unable to search right now.' } finally { loading.value = false }
    }
    onMounted(() => { loadBangs().catch(() => {}) })
    return { query, maxResults, hidePromoted, strictPrivacy, loading, error, results, sources, bangs, activeTab, bangRedirect, googleProxyUrl, tabs, visibleResults, domainOf, rank, search, icons }
  },
  template: `
  <main class="min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.24),_transparent_34%),linear-gradient(135deg,#020617,#0f172a_48%,#111827)] text-white">
    <section class="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
      <header class="flex flex-col gap-4 border-b border-white/10 pb-5 md:flex-row md:items-center md:justify-between"><div class="flex items-center gap-3"><div class="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-400 text-slate-950 shadow-lg shadow-emerald-950/30"><span class="h-7 w-7" v-html="icons.shield"></span></div><div><p class="text-xs uppercase tracking-[0.35em] text-emerald-200">OKNLAB</p><h1 class="text-2xl font-black tracking-tight">Privacy Search</h1></div></div><div class="flex flex-wrap gap-2 text-xs text-slate-300"><span class="badge badge-success badge-outline">No tracking</span><span class="badge badge-success badge-outline">No cookies</span><span class="badge badge-success badge-outline">Ad-free</span><span class="badge badge-success badge-outline">Anonymous View</span></div></header>
      <section class="grid flex-1 gap-8 py-10 lg:grid-cols-[0.9fr_1.4fr] lg:items-start"><div class="space-y-5"><div><p class="mb-3 inline-flex rounded-full border border-emerald-300/30 bg-emerald-300/10 px-4 py-2 text-sm text-emerald-100">Independent index + optional fallback + JSON API</p><h2 class="text-5xl font-black leading-tight tracking-tight md:text-6xl">Search without becoming the product.</h2><p class="mt-5 max-w-xl text-lg leading-8 text-slate-300">Bangs, multi-source results, strict privacy mode, anonymous link opening, and manual site ranking all in one Vue 3 interface.</p></div>
        <article class="rounded-3xl border border-white/10 bg-slate-900/65 p-5 shadow-2xl shadow-slate-950/30 backdrop-blur"><form class="space-y-4" @submit.prevent="search"><div class="flex gap-2"><input v-model="query" placeholder="Search, or try !w FastAPI / !yt Vue 3" class="h-14 w-full rounded-2xl border border-white/10 bg-white/10 px-5 text-base text-white placeholder:text-slate-400 outline-none transition focus:border-emerald-300/70 focus:bg-white/15 focus:ring-4 focus:ring-emerald-400/10" /><button class="inline-flex h-14 items-center justify-center gap-2 rounded-xl bg-emerald-400 px-7 font-semibold text-slate-950 shadow-lg shadow-emerald-950/20 hover:bg-emerald-300" :disabled="loading"><span class="h-5 w-5" v-html="icons.search"></span>{{ loading ? 'Searching' : 'Search' }}</button></div><div class="grid gap-3 sm:grid-cols-3"><label class="flex items-center gap-3 rounded-2xl bg-white/5 p-3 text-sm"><input v-model="hidePromoted" type="checkbox" class="toggle toggle-success" /> Hide promoted</label><label class="flex items-center gap-3 rounded-2xl bg-white/5 p-3 text-sm"><input v-model="strictPrivacy" type="checkbox" class="toggle toggle-success" /> Strict privacy</label><label class="rounded-2xl bg-white/5 p-3 text-sm">Results <input v-model="maxResults" type="range" min="3" max="20" class="range range-success range-xs mt-2" /></label></div></form></article>
        <article class="rounded-3xl border border-white/10 bg-slate-900/65 p-5 shadow-2xl shadow-slate-950/30 backdrop-blur"><h3 class="mb-3 font-bold">Bangs</h3><div class="flex flex-wrap gap-2"><button v-for="bang in bangs" :key="bang.bang" class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-slate-200 hover:bg-white/10" @click="query = bang.bang + ' '">{{ bang.bang }} {{ bang.name }}</button></div></article></div>
        <div class="space-y-4"><article v-if="bangRedirect" class="rounded-3xl border border-white/10 bg-slate-900/65 p-5 text-center shadow-2xl"><h3 class="text-xl font-bold">Bang detected</h3><p class="mt-2 text-slate-300">Open your destination through the anonymous view proxy.</p><a class="mt-4 inline-flex h-11 items-center rounded-xl bg-emerald-400 px-5 font-semibold text-slate-950" :href="bangRedirect">Open anonymously</a></article><div v-if="error" class="alert alert-error">{{ error }}</div>
          <article class="rounded-3xl border border-white/10 bg-slate-900/65 p-5 shadow-2xl shadow-slate-950/30 backdrop-blur"><div class="mb-4 flex flex-wrap items-center justify-between gap-3"><div class="tabs tabs-boxed bg-white/5"><button v-for="tab in tabs" :key="tab.id" class="tab gap-2 text-slate-300" :class="activeTab === tab.id && 'tab-active !bg-emerald-400 !text-slate-950'" @click="activeTab = tab.id">{{ tab.label }}</button></div><a v-if="googleProxyUrl" class="inline-flex h-9 items-center rounded-xl border border-emerald-300/40 px-3 text-sm text-emerald-100 hover:bg-emerald-300/10" :href="googleProxyUrl">Google via proxy</a></div><div v-if="loading" class="space-y-3"><div v-for="i in 4" :key="i" class="skeleton h-28 w-full bg-white/10"></div></div><div v-else-if="!visibleResults.length" class="rounded-2xl border border-dashed border-white/10 p-10 text-center text-slate-400">Run a search to see ad-free results.</div><div v-else-if="activeTab === 'images'" class="grid gap-4 sm:grid-cols-2"><a v-for="item in visibleResults" :key="item.image_url" :href="item.anonymous_url" class="group overflow-hidden rounded-2xl border border-white/10 bg-white/5"><img :src="item.image_url" :alt="item.title" class="h-44 w-full object-cover transition group-hover:scale-105" loading="lazy" /><div class="p-3 text-sm text-slate-200">{{ item.title }}</div></a></div><div v-else class="space-y-4"><article v-for="item in visibleResults" :key="item.url" class="rounded-2xl border border-white/10 bg-white/[0.04] p-4 transition hover:border-emerald-300/30 hover:bg-white/[0.07]"><div class="flex flex-wrap items-start justify-between gap-3"><div><p class="text-sm text-emerald-200">{{ item.source_name || domainOf(item.url) }}</p><a :href="item.url" class="text-xl font-bold text-white hover:text-emerald-200">{{ item.title }}</a></div><div class="flex gap-2"><button class="inline-flex h-9 items-center gap-2 rounded-xl px-3 text-sm text-slate-200 hover:bg-white/10" @click="rank(item.url, 1)"><span class="h-4 w-4" v-html="icons.star"></span> Rank</button><a class="inline-flex h-9 items-center gap-2 rounded-xl border border-white/10 bg-white/10 px-3 text-sm text-white hover:bg-white/15" :href="item.anonymous_url"><span class="h-4 w-4" v-html="icons.eye"></span> Anonymous View</a></div></div><p class="mt-3 line-clamp-3 text-sm leading-6 text-slate-300">{{ item.content }}</p></article></div></article></div>
      </section><footer class="border-t border-white/10 py-5 text-center text-sm text-slate-400">Built by OKNLAB</footer></section></main>`,
}).mount('#app')
