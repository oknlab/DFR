import { createApp, computed, onMounted, ref } from 'https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.esm-browser.prod.js'

const icons = {
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Z"/><path d="m9 12 2 2 4-4"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
  eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m2 2 20 20"/><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 4.2A10.8 10.8 0 0 1 12 4c7 0 10 8 10 8a13.2 13.2 0 0 1-2.2 3.3"/><path d="M6.6 6.6C3.5 8.7 2 12 2 12s3 8 10 8c1.4 0 2.7-.3 3.8-.8"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.3L5.8 21 7 14.2 2 9.3l6.9-1L12 2Z"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z"/></svg>',
  globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 0 20"/><path d="M12 2a15.3 15.3 0 0 0 0 20"/></svg>',
  image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/></svg>',
  news: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 22h16a2 2 0 0 0 2-2V4H2v16a2 2 0 0 0 2 2Z"/><path d="M7 8h10"/><path d="M7 12h10"/><path d="M7 16h6"/></svg>',
  docs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/></svg>',
  social: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  tune: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M2 14h4"/><path d="M10 8h4"/><path d="M18 16h4"/></svg>',
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
    const lastQuery = ref('')
    const rankings = ref(JSON.parse(localStorage.getItem('oknlab-rankings') || '{}'))

    const tabs = [
      { id: 'web', label: 'Web', icon: 'globe' },
      { id: 'images', label: 'Images', icon: 'image' },
      { id: 'news', label: 'News', icon: 'news' },
      { id: 'documents', label: 'Docs', icon: 'docs' },
      { id: 'social', label: 'Social', icon: 'social' },
    ]

    const privacyStats = [
      { label: 'Trackers', value: '0', hint: 'No analytics scripts' },
      { label: 'Cookies', value: '0', hint: 'No identity storage' },
      { label: 'Ads', value: '0', hint: 'Promotions filtered' },
    ]

    const quickSearches = ['!w differential privacy', '!yt vue 3 search ui', '!amazon privacy screen', 'open source search engine']

    const visibleResults = computed(() => {
      if (activeTab.value === 'web') return results.value
      return sources.value?.[activeTab.value] || []
    })

    const totalSources = computed(() => Object.values(sources.value || {}).reduce((sum, list) => sum + (list?.length || 0), 0))
    const rankedDomains = computed(() => Object.entries(rankings.value).sort((a, b) => b[1] - a[1]).slice(0, 5))

    const domainOf = (url) => {
      try {
        return new URL(url).hostname.replace('www.', '')
      } catch {
        return 'unknown source'
      }
    }

    const formatSnippet = (text = '') => text.length > 280 ? `${text.slice(0, 280)}…` : text

    const setQuickSearch = (value) => {
      query.value = value
      search()
    }

    const rank = (url, delta) => {
      const domain = domainOf(url)
      rankings.value = { ...rankings.value, [domain]: (rankings.value[domain] || 0) + delta }
      localStorage.setItem('oknlab-rankings', JSON.stringify(rankings.value))
      results.value = [...results.value].sort((a, b) => (rankings.value[domainOf(b.url)] || 0) - (rankings.value[domainOf(a.url)] || 0))
    }

    const loadBangs = async () => {
      const response = await fetch('/api/bangs')
      bangs.value = await response.json()
    }

    const search = async () => {
      if (!query.value.trim()) return
      loading.value = true
      error.value = ''
      bangRedirect.value = ''
      lastQuery.value = query.value.trim()
      try {
        const response = await fetch('/api/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query.value,
            max_results: Number(maxResults.value),
            hide_promoted: hidePromoted.value,
            strict_privacy: strictPrivacy.value,
            rankings: rankings.value,
          }),
        })
        if (!response.ok) throw new Error(`Search failed (${response.status})`)
        const data = await response.json()
        if (data.bang_redirect) {
          bangRedirect.value = data.bang_redirect
          results.value = []
          sources.value = { web: [], documents: [], images: [], news: [], social: [] }
          return
        }
        results.value = data.results || []
        sources.value = data.sources || { web: [], documents: [], images: [], news: [], social: [] }
        googleProxyUrl.value = data.google_proxy_url
      } catch (err) {
        error.value = err.message || 'Unable to search right now.'
      } finally {
        loading.value = false
      }
    }

    onMounted(() => { loadBangs().catch(() => {}) })

    return {
      query,
      maxResults,
      hidePromoted,
      strictPrivacy,
      loading,
      error,
      results,
      sources,
      bangs,
      activeTab,
      bangRedirect,
      googleProxyUrl,
      lastQuery,
      rankings,
      tabs,
      privacyStats,
      quickSearches,
      visibleResults,
      totalSources,
      rankedDomains,
      domainOf,
      formatSnippet,
      setQuickSearch,
      rank,
      search,
      icons,
    }
  },
  template: `
    <main class="app-shell min-h-screen text-slate-100">
      <div class="pointer-events-none fixed inset-0 overflow-hidden">
        <div class="aurora aurora-one"></div>
        <div class="aurora aurora-two"></div>
        <div class="aurora aurora-three"></div>
      </div>

      <section class="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header class="glass-card sticky top-4 z-20 flex flex-col gap-4 rounded-[2rem] px-5 py-4 md:flex-row md:items-center md:justify-between">
          <a href="/" class="flex items-center gap-3">
            <span class="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-emerald-300 to-cyan-300 text-slate-950 shadow-lg shadow-emerald-950/30">
              <span class="h-7 w-7" v-html="icons.shield"></span>
            </span>
            <span>
              <span class="block text-xs font-bold uppercase tracking-[0.35em] text-emerald-200">OKNLAB</span>
              <span class="block text-xl font-black tracking-tight text-white">Privacy Search</span>
            </span>
          </a>
          <nav class="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-300">
            <span class="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 text-emerald-100">No tracking</span>
            <span class="rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1.5 text-cyan-100">No cookies</span>
            <span class="rounded-full border border-violet-300/25 bg-violet-300/10 px-3 py-1.5 text-violet-100">Ad-free</span>
            <span class="rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1.5 text-amber-100">Anonymous View</span>
          </nav>
        </header>

        <section class="grid flex-1 gap-6 py-8 lg:grid-cols-[minmax(0,1.02fr)_390px] xl:grid-cols-[minmax(0,1.1fr)_420px]">
          <div class="space-y-6">
            <section class="hero-card overflow-hidden rounded-[2.25rem] p-6 sm:p-8 lg:p-10">
              <div class="max-w-4xl">
                <div class="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-4 py-2 text-sm font-semibold text-emerald-100 shadow-2xl shadow-slate-950/20 backdrop-blur">
                  <span class="h-4 w-4" v-html="icons.spark"></span>
                  Independent index • Anonymous proxy • JSON API
                </div>
                <h1 class="max-w-4xl text-4xl font-black leading-[0.95] tracking-[-0.06em] text-white sm:text-6xl lg:text-7xl">
                  Search the web without leaving a shadow profile.
                </h1>
                <p class="mt-5 max-w-2xl text-base leading-8 text-slate-300 sm:text-lg">
                  OKNLAB combines bangs, multi-source results, local manual ranking, strict privacy controls, and anonymous link opening in one polished search workspace.
                </p>
              </div>

              <form class="mt-8 rounded-[2rem] border border-white/10 bg-slate-950/65 p-2 shadow-2xl shadow-slate-950/40 backdrop-blur-xl" @submit.prevent="search">
                <div class="flex flex-col gap-2 md:flex-row">
                  <label class="group flex min-h-16 flex-1 items-center gap-3 rounded-[1.5rem] bg-white/[0.06] px-5 ring-1 ring-white/10 transition focus-within:bg-white/[0.1] focus-within:ring-emerald-300/60">
                    <span class="h-5 w-5 text-emerald-200" v-html="icons.search"></span>
                    <input
                      v-model="query"
                      class="w-full bg-transparent text-lg font-semibold text-white placeholder:text-slate-500 focus:outline-none"
                      autocomplete="off"
                      placeholder="Search privately, or try !w FastAPI / !yt Vue 3"
                    />
                  </label>
                  <button class="inline-flex min-h-16 items-center justify-center gap-3 rounded-[1.5rem] bg-gradient-to-r from-emerald-300 to-cyan-300 px-7 text-base font-black text-slate-950 shadow-xl shadow-emerald-950/30 transition hover:scale-[1.01] hover:shadow-emerald-700/20 disabled:cursor-not-allowed disabled:opacity-70" :disabled="loading">
                    <span class="h-5 w-5" v-html="icons.search"></span>
                    {{ loading ? 'Searching…' : 'Search' }}
                  </button>
                </div>

                <div class="grid gap-2 p-2 pt-4 sm:grid-cols-3">
                  <label class="control-tile">
                    <input v-model="hidePromoted" type="checkbox" class="toggle toggle-success toggle-sm" />
                    <span><strong>Hide promoted</strong><small>Ad-free results</small></span>
                  </label>
                  <label class="control-tile">
                    <input v-model="strictPrivacy" type="checkbox" class="toggle toggle-success toggle-sm" />
                    <span><strong>Strict privacy</strong><small>No IP/cookie storage</small></span>
                  </label>
                  <label class="control-tile block">
                    <span class="mb-2 flex items-center justify-between"><strong>{{ maxResults }} results</strong><small>Depth</small></span>
                    <input v-model="maxResults" type="range" min="3" max="20" class="range range-success range-xs" />
                  </label>
                </div>
              </form>

              <div class="mt-5 flex flex-wrap gap-2">
                <button
                  v-for="item in quickSearches"
                  :key="item"
                  class="rounded-full border border-white/10 bg-white/[0.07] px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-emerald-300/40 hover:bg-emerald-300/10 hover:text-emerald-100"
                  @click="setQuickSearch(item)"
                >
                  {{ item }}
                </button>
              </div>
            </section>

            <section class="grid gap-4 md:grid-cols-3">
              <article v-for="stat in privacyStats" :key="stat.label" class="glass-card rounded-[1.75rem] p-5">
                <p class="text-sm font-semibold text-slate-400">{{ stat.label }}</p>
                <div class="mt-2 flex items-end justify-between">
                  <strong class="text-5xl font-black text-white">{{ stat.value }}</strong>
                  <span class="rounded-full bg-emerald-300/10 px-3 py-1 text-xs font-bold text-emerald-200">{{ stat.hint }}</span>
                </div>
              </article>
            </section>

            <section class="glass-card rounded-[2rem] p-4 sm:p-5">
              <div class="flex flex-col gap-4 border-b border-white/10 pb-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <p class="text-sm font-bold uppercase tracking-[0.25em] text-emerald-200">Results workspace</p>
                  <h2 class="mt-1 text-2xl font-black text-white">{{ lastQuery ? 'Results for “' + lastQuery + '”' : 'Ready for private search' }}</h2>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="tab in tabs"
                    :key="tab.id"
                    class="tab-button"
                    :class="activeTab === tab.id && 'tab-button-active'"
                    @click="activeTab = tab.id"
                  >
                    <span class="h-4 w-4" v-html="icons[tab.icon]"></span>
                    {{ tab.label }}
                    <span class="rounded-full bg-white/10 px-2 py-0.5 text-[10px]">{{ tab.id === 'web' ? results.length : (sources[tab.id]?.length || 0) }}</span>
                  </button>
                </div>
              </div>

              <div v-if="error" class="alert alert-error mt-5 rounded-2xl border border-red-300/20 bg-red-500/10 text-red-100">{{ error }}</div>

              <article v-if="bangRedirect" class="mt-5 rounded-[1.75rem] border border-emerald-300/20 bg-emerald-300/10 p-6 text-center">
                <p class="text-sm font-bold uppercase tracking-[0.25em] text-emerald-200">Bang detected</p>
                <h3 class="mt-2 text-2xl font-black text-white">Open through Anonymous View</h3>
                <p class="mt-2 text-slate-300">Your bang shortcut is ready without creating a profile trail.</p>
                <a class="mt-5 inline-flex items-center justify-center gap-2 rounded-2xl bg-emerald-300 px-5 py-3 font-black text-slate-950" :href="bangRedirect">
                  <span class="h-5 w-5" v-html="icons.eye"></span>
                  Open anonymously
                </a>
              </article>

              <div v-if="loading" class="mt-5 space-y-4">
                <div v-for="i in 4" :key="i" class="skeleton-card"></div>
              </div>

              <div v-else-if="!visibleResults.length && !bangRedirect" class="empty-state mt-5 rounded-[1.75rem] p-8 text-center sm:p-12">
                <div class="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-emerald-300/10 text-emerald-200 ring-1 ring-emerald-300/20">
                  <span class="h-8 w-8" v-html="icons.lock"></span>
                </div>
                <h3 class="mt-5 text-2xl font-black text-white">Private search starts here</h3>
                <p class="mx-auto mt-2 max-w-xl text-slate-400">Use the search bar above to query the independent index, trigger a bang, or open Google through the anonymous proxy.</p>
              </div>

              <div v-else-if="activeTab === 'images'" class="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                <a
                  v-for="item in visibleResults"
                  :key="item.image_url"
                  :href="item.anonymous_url || item.url"
                  class="image-card group"
                >
                  <img :src="item.image_url" :alt="item.title" loading="lazy" />
                  <span>{{ item.title }}</span>
                </a>
              </div>

              <div v-else class="mt-5 space-y-4">
                <article v-for="item in visibleResults" :key="item.url" class="result-card group">
                  <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div class="min-w-0">
                      <p class="flex flex-wrap items-center gap-2 text-sm font-semibold text-emerald-200">
                        <span>{{ item.source_name || domainOf(item.url) }}</span>
                        <span v-if="item.is_promoted" class="rounded-full bg-amber-300/10 px-2 py-0.5 text-xs text-amber-100">promoted</span>
                        <span v-if="rankings[domainOf(item.url)]" class="rounded-full bg-violet-300/10 px-2 py-0.5 text-xs text-violet-100">rank {{ rankings[domainOf(item.url)] }}</span>
                      </p>
                      <a :href="item.url" class="mt-1 block truncate text-xl font-black text-white transition group-hover:text-emerald-100">{{ item.title }}</a>
                    </div>
                    <div class="flex shrink-0 gap-2">
                      <button class="shadcn-button shadcn-button-ghost" @click="rank(item.url, 1)">
                        <span class="h-4 w-4" v-html="icons.star"></span>
                        Rank
                      </button>
                      <a class="shadcn-button shadcn-button-secondary" :href="item.anonymous_url">
                        <span class="h-4 w-4" v-html="icons.eye"></span>
                        Anonymous View
                      </a>
                    </div>
                  </div>
                  <p class="mt-3 text-sm leading-7 text-slate-300">{{ formatSnippet(item.content) }}</p>
                  <div class="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span class="rounded-full bg-white/[0.06] px-3 py-1">JSON API result</span>
                    <span class="rounded-full bg-white/[0.06] px-3 py-1">No tracking token</span>
                    <span class="rounded-full bg-white/[0.06] px-3 py-1">{{ domainOf(item.url) }}</span>
                  </div>
                </article>
              </div>
            </section>
          </div>

          <aside class="space-y-5 lg:sticky lg:top-28 lg:self-start">
            <section class="glass-card rounded-[2rem] p-5">
              <div class="flex items-center gap-3">
                <span class="grid h-11 w-11 place-items-center rounded-2xl bg-emerald-300/10 text-emerald-200 ring-1 ring-emerald-300/20">
                  <span class="h-5 w-5" v-html="icons.tune"></span>
                </span>
                <div>
                  <h2 class="text-lg font-black text-white">Privacy console</h2>
                  <p class="text-sm text-slate-400">Local controls, no profiling.</p>
                </div>
              </div>
              <div class="mt-5 space-y-3">
                <div class="console-row"><span>Tracking</span><strong>Disabled</strong></div>
                <div class="console-row"><span>Cookie storage</span><strong>Blocked</strong></div>
                <div class="console-row"><span>IP logging</span><strong>Off</strong></div>
                <div class="console-row"><span>Sources indexed</span><strong>{{ totalSources }}</strong></div>
              </div>
            </section>

            <section class="glass-card rounded-[2rem] p-5">
              <div class="mb-4 flex items-center justify-between">
                <h2 class="text-lg font-black text-white">Bangs</h2>
                <span class="rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-slate-300">{{ bangs.length }} loaded</span>
              </div>
              <div class="grid gap-2">
                <button
                  v-for="bang in bangs"
                  :key="bang.bang"
                  class="bang-row"
                  @click="query = bang.bang + ' '"
                >
                  <span class="font-black text-emerald-200">{{ bang.bang }}</span>
                  <span class="min-w-0 flex-1 truncate text-left text-slate-200">{{ bang.name }}</span>
                  <span class="text-xs text-slate-500">{{ bang.category }}</span>
                </button>
              </div>
            </section>

            <section class="glass-card rounded-[2rem] p-5">
              <div class="mb-4 flex items-center justify-between">
                <h2 class="text-lg font-black text-white">Personal ranking</h2>
                <span class="h-5 w-5 text-violet-200" v-html="icons.star"></span>
              </div>
              <div v-if="rankedDomains.length" class="space-y-2">
                <div v-for="[domain, score] in rankedDomains" :key="domain" class="rank-row">
                  <span class="truncate">{{ domain }}</span>
                  <strong>+{{ score }}</strong>
                </div>
              </div>
              <p v-else class="rounded-2xl border border-dashed border-white/10 p-4 text-sm leading-6 text-slate-400">
                Click Rank on results to personalize ordering. Rankings stay in your browser only.
              </p>
            </section>

            <section class="rounded-[2rem] border border-emerald-300/20 bg-gradient-to-br from-emerald-300/15 to-cyan-300/10 p-5 shadow-2xl shadow-slate-950/30">
              <p class="text-sm font-bold uppercase tracking-[0.25em] text-emerald-100">Proxy integration</p>
              <h2 class="mt-2 text-xl font-black text-white">Anonymous View for every link</h2>
              <p class="mt-2 text-sm leading-6 text-slate-300">Open results through the proxy route with no referrer, no cookies, and no profile handoff.</p>
              <a v-if="googleProxyUrl" class="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-white px-4 py-3 font-black text-slate-950" :href="googleProxyUrl">
                <span class="h-4 w-4" v-html="icons.globe"></span>
                Google via proxy
              </a>
            </section>
          </aside>
        </section>

        <footer class="relative border-t border-white/10 py-6 text-center text-sm font-semibold text-slate-400">
          Built by OKNLAB
        </footer>
      </section>
    </main>
  `,
}).mount('#app')
