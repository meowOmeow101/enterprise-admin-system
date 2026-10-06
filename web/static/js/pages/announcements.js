/* ==========================================================================
   公告通知：列表、已读回执、发布与管理
   ========================================================================== */
(function () {
  'use strict';

  window.PageAnnouncements = {
    inject: ['refreshBadges'],
    data: function () {
      return {
        loading: false,
        rows: [], total: 0, page: 1, size: 10, pages: 1, unread: 0,
        categories: [],
        query: { keyword: '', category: '', only_unread: false, include_draft: false },

        showDetail: false, detail: null,
        showForm: false, saving: false,
        form: { id: null, title: '', content: '', category: '通知', is_pinned: false,
                is_published: true },
      };
    },
    computed: {
      canPublish: function () { return App.isManager(); },
      isAdmin: function () { return App.isAdmin(); },
    },
    mounted: function () { this.load(); },
    methods: {
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ page: this.page, size: this.size }, this.query);
          const res = await API.announcements.list(params);
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
          this.unread = res.unread;
          if (res.categories) this.categories = res.categories;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { keyword: '', category: '', only_unread: false, include_draft: false };
        this.search();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },

      open: async function (row) {
        try {
          this.detail = await API.announcements.get(row.id);
          this.showDetail = true;
          // 标记已读后刷新列表与角标
          this.load();
          this.refreshBadges();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      openCreate: function () {
        this.form = { id: null, title: '', content: '', category: '通知', is_pinned: false,
                      is_published: true };
        this.showForm = true;
      },
      openEdit: function (row) {
        this.form = { id: row.id, title: row.title, content: row.content,
                      category: row.category, is_pinned: row.is_pinned,
                      is_published: row.is_published };
        this.showForm = true;
      },
      save: async function () {
        if (!this.form.title.trim()) { App.toast('请填写公告标题', 'error'); return; }
        if (!this.form.content.trim()) { App.toast('请填写公告内容', 'error'); return; }
        this.saving = true;
        try {
          const payload = {
            title: this.form.title, content: this.form.content,
            category: this.form.category, is_pinned: this.form.is_pinned,
            is_published: this.form.is_published,
          };
          if (this.form.id) {
            await API.announcements.update(this.form.id, payload);
            App.toast('公告已更新', 'success');
          } else {
            await API.announcements.create(payload);
            App.toast('公告已发布', 'success');
          }
          this.showForm = false;
          this.load();
          this.refreshBadges();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      togglePin: async function (row) {
        try {
          await API.announcements.patch(row.id, { is_pinned: !row.is_pinned });
          App.toast(row.is_pinned ? '已取消置顶' : '已置顶', 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      remove: async function (row) {
        const ok = await App.confirm({
          title: '删除公告', message: '确定要删除公告《' + row.title + '》吗？',
          detail: '删除后员工将无法再看到这条公告。', danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.announcements.remove(row.id);
          App.toast(res.message, 'success');
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },
      canEdit: function (row) {
        return App.isManager() && (this.isAdmin || (App.user && row.publisher_id === App.user.id));
      },
      fromNow: function (v) { return App.fromNow(v); },
      fmt: function (v) { return App.dateOnly(v); },
    },
    template: `
      <div>
        <div class="grid c3 mb2">
          <stat-card label="公告总数" :value="total" :foot="query.only_unread ? '仅看未读' : '全部公告'"
                     accent="1" icon="📢"></stat-card>
          <stat-card label="未读公告" :value="unread" foot="点击公告即标记为已读" accent="3"
                     icon="🔔"></stat-card>
          <stat-card label="置顶公告" :value="rows.filter(function(r){return r.is_pinned}).length"
                     foot="当前页置顶数量" accent="4" icon="📌"></stat-card>
        </div>

        <div class="card">
          <div class="filters">
            <input class="grow" type="text" v-model="query.keyword" @keyup.enter="search"
                   placeholder="搜索公告标题或内容 ...">
            <select v-model="query.category" @change="search">
              <option value="">全部分类</option>
              <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
            </select>
            <label class="fs13 flex-center gap1" style="cursor:pointer">
              <input type="checkbox" v-model="query.only_unread" @change="search" style="width:auto">
              只看未读
            </label>
            <label class="fs13 flex-center gap1" style="cursor:pointer" v-if="canPublish">
              <input type="checkbox" v-model="query.include_draft" @change="search" style="width:auto">
              含草稿
            </label>
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>
            <div class="spacer"></div>
            <button class="btn primary" v-if="canPublish" @click="openCreate">➕ 发布公告</button>
          </div>

          <div class="card-body">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="📢" text="暂无公告"
                         hint="有重要事项可以通过右上角发布公告通知全员"></empty-state>

            <div v-else>
              <div v-for="a in rows" :key="a.id"
                   style="padding:14px 0;border-bottom:1px dashed #eef2f7">
                <div class="flex-between wrap gap2">
                  <div style="flex:1;min-width:0">
                    <div class="flex-center gap1 wrap">
                      <span class="tag red" v-if="a.is_pinned">📌 置顶</span>
                      <span class="tag blue">{{ a.category }}</span>
                      <span class="tag gray" v-if="!a.is_published">草稿</span>
                      <span class="tag yellow" v-if="!a.is_read && a.is_published">未读</span>
                      <span class="strong link" style="font-size:15px" @click="open(a)">
                        {{ a.title }}
                      </span>
                    </div>
                    <div class="fs12 text-light mt1">
                      {{ a.publisher_name || '系统' }} 发布于 {{ fmt(a.created_at) }}
                       · 已读 {{ a.read_count }} 人
                    </div>
                    <div class="fs13 text-muted mt1" style="line-height:1.7">
                      {{ (a.content || '').slice(0, 110) }}{{ (a.content || '').length > 110 ? ' ...' : '' }}
                    </div>
                  </div>
                  <div class="btn-group">
                    <button class="btn sm" @click="open(a)">查看全文</button>
                    <template v-if="canEdit(a)">
                      <button class="btn sm" @click="togglePin(a)">
                        {{ a.is_pinned ? '取消置顶' : '置顶' }}
                      </button>
                      <button class="btn sm" @click="openEdit(a)">编辑</button>
                      <button class="btn sm danger" @click="remove(a)">删除</button>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>

        <!-- ================= 公告详情 ================= -->
        <modal v-if="showDetail && detail" :title="detail.title" size="wide" :hideFooter="true"
               @close="showDetail = false">
          <div class="flex-center gap1 mb2 wrap">
            <span class="tag red" v-if="detail.is_pinned">📌 置顶</span>
            <span class="tag blue">{{ detail.category }}</span>
            <span class="fs12 text-light">
              {{ detail.publisher_name || '系统' }} · {{ App.dateTime(detail.created_at) }}
              · 已读 {{ detail.read_count }} 人
            </span>
          </div>
          <announcement-body :content="detail.content"></announcement-body>
          <div class="fs12 text-light mt3" v-if="detail.readers && detail.readers.length">
            已读人员：{{ detail.readers.join('、') }}
          </div>
        </modal>

        <!-- ================= 发布 / 编辑 ================= -->
        <modal v-if="showForm" :title="form.id ? '编辑公告' : '发布公告'" size="wide"
               :loading="saving" @close="showForm = false" @ok="save">
          <div class="form-grid c2">
            <div class="form-item full">
              <label>公告标题 <span class="req">*</span></label>
              <input type="text" v-model="form.title" placeholder="如 关于 2025 年度绩效考核安排的通知">
            </div>
            <div class="form-item">
              <label>分类</label>
              <select v-model="form.category">
                <option v-for="c in (categories.length ? categories : ['通知'])" :key="c" :value="c">
                  {{ c }}
                </option>
              </select>
            </div>
            <div class="form-item">
              <label>发布设置</label>
              <div class="btn-group">
                <label class="fs13 flex-center gap1" style="cursor:pointer">
                  <input type="checkbox" v-model="form.is_pinned" style="width:auto"> 置顶显示
                </label>
                <label class="fs13 flex-center gap1" style="cursor:pointer">
                  <input type="checkbox" v-model="form.is_published" style="width:auto"> 立即发布
                </label>
              </div>
              <span class="hint">取消勾选「立即发布」则保存为草稿，员工看不到</span>
            </div>
            <div class="form-item full">
              <label>公告内容 <span class="req">*</span></label>
              <textarea v-model="form.content" style="min-height:220px"
                        placeholder="支持换行分段，直接写正文即可"></textarea>
            </div>
          </div>
        </modal>
      </div>`,
  };
})();
