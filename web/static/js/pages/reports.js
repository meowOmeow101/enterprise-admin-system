/* ==========================================================================
   报告管理：上传（拖拽）、分类筛选、版本追溯、下载与在线预览
   ========================================================================== */
(function () {
  'use strict';

  window.PageReports = {
    data: function () {
      return {
        loading: true,
        rows: [], total: 0, page: 1, size: 20, pages: 1,
        projects: [], categories: [],
        query: { keyword: '', project_id: null, category: '', date_from: '', date_to: '' },
        stats: null,
        selected: [],

        // 上传表单：不单独开弹窗，直接嵌在页面顶部，上传更顺手
        up: {
          file: null, title: '', category: '周报', project_id: null,
          report_date: App.today(), tags: '', summary: '',
        },
        dragging: false,
        uploading: false,
        uploadProgress: '',

        // 版本历史
        showVersions: false, versionTitle: '', versions: [], versionLoading: false,
        // 编辑元信息
        showEdit: false, editForm: { id: null, title: '', category: '', tags: '', summary: '', report_date: '' },
        saving: false,
      };
    },
    computed: {
      canUpload: function () { return !!API.store.token; },
      selectedProjects: function () { return this.projects; },
      allChecked: function () { return this.rows.length > 0 && this.selected.length === this.rows.length; },
    },
    mounted: function () { this.init(); },
    methods: {
      init: async function () {
        try {
          const [p, c] = await Promise.all([API.projects.options(), API.reports.categories()]);
          this.projects = p.items;
          this.categories = c.items;
        } catch (e) { App.toast(e.message, 'error'); }
        this.load();
        this.loadStats();
      },
      load: async function () {
        this.loading = true;
        try {
          const params = Object.assign({ page: this.page, size: this.size }, this.query);
          const res = await API.reports.list(params);
          this.rows = res.items;
          this.total = res.total;
          this.pages = res.pages;
          this.selected = [];
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.loading = false; }
      },
      loadStats: async function () {
        try { this.stats = await API.reports.stats(); } catch (e) { /* 忽略 */ }
      },
      search: function () { this.page = 1; this.load(); },
      reset: function () {
        this.query = { keyword: '', project_id: null, category: '', date_from: '', date_to: '' };
        this.page = 1;
        this.load();
      },
      changePage: function (p) { this.page = p; this.load(); },
      changeSize: function (s) { this.size = s; this.page = 1; this.load(); },

      /* ------------------------------------------------ 上传 */
      pickFile: function (e) {
        const f = e.target.files[0];
        if (f) this.acceptFile(f);
        e.target.value = '';        // 允许重复选同一个文件
      },
      onDrop: function (e) {
        this.dragging = false;
        const f = e.dataTransfer.files[0];
        if (f) this.acceptFile(f);
      },
      acceptFile: function (f) {
        this.up.file = f;
        // 标题留空时用文件名（去掉扩展名）兜底
        if (!this.up.title) this.up.title = f.name.replace(/\.[^.]+$/, '');
        this.uploadProgress = '';
      },
      clearFile: function () { this.up.file = null; this.uploadProgress = ''; },
      doUpload: async function () {
        if (!this.up.file) { App.toast('请先选择要上传的文件', 'warning'); return; }
        if (!this.up.title) { App.toast('请填写报告标题', 'warning'); return; }
        this.uploading = true;
        this.uploadProgress = '正在上传 ...';
        try {
          const fd = new FormData();
          fd.append('file', this.up.file);
          fd.append('title', this.up.title);
          fd.append('category', this.up.category);
          if (this.up.project_id) fd.append('project_id', String(this.up.project_id));
          if (this.up.report_date) fd.append('report_date', this.up.report_date);
          if (this.up.tags) fd.append('tags', this.up.tags);
          if (this.up.summary) fd.append('summary', this.up.summary);

          const res = await API.reports.upload(fd);
          App.toast(res.message, 'success');
          this.up.file = null;
          this.up.title = '';
          this.up.tags = '';
          this.up.summary = '';
          this.uploadProgress = '';
          this.load();
          this.loadStats();
          this.refreshBadges && this.refreshBadges();
        } catch (e) {
          this.uploadProgress = '';
          App.toast(e.message, 'error');
        } finally { this.uploading = false; }
      },

      /* ------------------------------------------------ 下载 / 预览 */
      download: async function (row) {
        try {
          await API.reports.download(row.id, row.file_name);
          App.toast('正在下载：' + row.file_name, 'success');
          this.load();     // 刷新下载次数
        } catch (e) { App.toast(e.message, 'error'); }
      },
      preview: async function (row) {
        if (!row.is_previewable) { App.toast('该文件类型不支持在线预览，请下载后查看', 'warning'); return; }
        try {
          await API.reports.preview(row.id);
          App.toast('已在新标签页打开预览', 'success');
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 版本 */
      openVersions: async function (row) {
        this.showVersions = true;
        this.versionTitle = row.title;
        this.versionLoading = true;
        try {
          const res = await API.reports.versions(row.id);
          this.versions = res.items;
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.versionLoading = false; }
      },

      /* ------------------------------------------------ 编辑与删除 */
      openEdit: function (row) {
        this.editForm = {
          id: row.id, title: row.title, category: row.category,
          tags: row.tags || '', summary: row.summary || '',
          report_date: App.dateOnly(row.report_date) === '—' ? '' : App.dateOnly(row.report_date),
        };
        this.showEdit = true;
      },
      saveEdit: async function () {
        this.saving = true;
        try {
          await API.reports.update(this.editForm.id, {
            title: this.editForm.title, category: this.editForm.category,
            tags: this.editForm.tags, summary: this.editForm.summary,
            report_date: this.editForm.report_date || null,
          });
          App.toast('报告信息已更新', 'success');
          this.showEdit = false;
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
        finally { this.saving = false; }
      },
      remove: async function (row) {
        const ok = await App.confirm({
          title: '删除报告',
          message: '确定要删除《' + row.title + '》v' + row.version + ' 吗？',
          detail: '对应的磁盘文件也会一并删除，且无法恢复。',
          danger: true, okText: '确认删除',
        });
        if (!ok) return;
        try {
          const res = await API.reports.remove(row.id);
          App.toast(res.message, 'success');
          this.load();
          this.loadStats();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 批量下载 */
      toggleAll: function (e) {
        this.selected = e.target.checked ? this.rows.map(function (r) { return r.id; }) : [];
      },
      toggleOne: function (id) {
        const i = this.selected.indexOf(id);
        if (i >= 0) this.selected.splice(i, 1); else this.selected.push(id);
      },
      batchDownload: async function () {
        if (!this.selected.length) return;
        try {
          const res = await API.reports.batch(this.selected);
          App.toast('开始逐个下载 ' + res.total + ' 份报告 ...', 'success');
          for (const item of res.items) {
            await API.download('/reports/' + item.id + '/download', item.file_name);
            await new Promise(function (r) { setTimeout(r, 260); });   // 稍作间隔，避免浏览器拦截
          }
          this.load();
        } catch (e) { App.toast(e.message, 'error'); }
      },

      /* ------------------------------------------------ 小工具 */
      fmt: function (v) { return App.dateOnly(v); },
      fileSize: function (v) { return App.fileSize(v); },
      tagList: function (v) { return App.tagList(v); },
      iconOf: function (ext) {
        const e = (ext || '').toLowerCase();
        if (e === '.pdf') return '📕';
        if (['.doc', '.docx'].indexOf(e) >= 0) return '📘';
        if (['.xls', '.xlsx', '.csv'].indexOf(e) >= 0) return '📗';
        if (['.ppt', '.pptx'].indexOf(e) >= 0) return '📙';
        if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].indexOf(e) >= 0) return '🖼️';
        if (['.zip', '.rar', '.7z'].indexOf(e) >= 0) return '🗜️';
        return '📄';
      },
    },
    template: `
      <div>
        <!-- ================= 统计 ================= -->
        <div class="grid c4 mb2" v-if="stats">
          <stat-card label="报告总数" :value="stats.total" foot="可见范围内的全部报告"
                     accent="1" icon="📄"></stat-card>
          <stat-card label="占用空间" :value="fileSize(stats.total_size)" foot="所有附件合计"
                     accent="4" icon="💾"></stat-card>
          <stat-card label="累计下载" :value="stats.total_downloads" foot="所有报告被下载次数"
                     accent="2" icon="📥"></stat-card>
          <stat-card label="分类数量" :value="Object.keys(stats.by_category).length"
                     foot="当前使用的报告分类" accent="3" icon="🏷️"></stat-card>
        </div>

        <!-- ================= 上传区 ================= -->
        <div class="card">
          <div class="card-head">
            <h3>上传报告</h3>
            <span class="sub">同一项目下「标题 + 分类」相同会自动记为新的版本，历史版本可随时下载</span>
          </div>
          <div class="card-body">
            <div class="grid c2" style="grid-template-columns: 1fr 1.3fr">
              <div class="file-drop" :class="{ over: dragging }"
                   @click="$refs.upFile.click()"
                   @dragover.prevent="dragging = true"
                   @dragleave.prevent="dragging = false"
                   @drop.prevent="onDrop">
                <div class="icon">{{ up.file ? iconOf(up.file.name.split('.').pop()) : '📤' }}</div>
                <div>{{ up.file ? '已选择文件' : '点击选择文件，或拖拽到此处' }}</div>
                <div class="tip">
                  支持 PDF / Word / Excel / PPT / 图片 / 压缩包，单个文件不超过 50 MB
                </div>
                <div class="fname" v-if="up.file">
                  {{ up.file.name }}（{{ fileSize(up.file.size) }}）
                  <span class="link" style="margin-left:8px" @click.stop="clearFile">移除</span>
                </div>
              </div>
              <input ref="upFile" type="file" style="display:none" @change="pickFile">

              <div class="form-grid c2">
                <div class="form-item">
                  <label>报告标题 <span class="req">*</span></label>
                  <input type="text" v-model="up.title" placeholder="如 第 12 周项目周报">
                </div>
                <div class="form-item">
                  <label>所属项目</label>
                  <select v-model="up.project_id">
                    <option :value="null">不关联项目（通用报告）</option>
                    <option v-for="p in projects" :key="p.id" :value="p.id">
                      {{ p.name }}{{ p.status ? '（' + p.status + '）' : '' }}
                    </option>
                  </select>
                </div>
                <div class="form-item">
                  <label>报告分类</label>
                  <select v-model="up.category">
                    <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
                  </select>
                </div>
                <div class="form-item">
                  <label>报告日期</label>
                  <input type="date" v-model="up.report_date">
                </div>
                <div class="form-item full">
                  <label>标签（用逗号分隔）</label>
                  <input type="text" v-model="up.tags" placeholder="如 迭代, 评审通过">
                </div>
                <div class="form-item full">
                  <label>摘要说明</label>
                  <textarea v-model="up.summary" style="min-height:52px"
                            placeholder="一句话说明这份报告的内容，方便他人检索"></textarea>
                </div>
                <div class="form-item full flex-between">
                  <span class="fs12 text-muted">{{ uploadProgress }}</span>
                  <button class="btn primary" :disabled="uploading" @click="doUpload">
                    {{ uploading ? '上传中 ...' : '⬆️ 上传报告' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ================= 列表 ================= -->
        <div class="card">
          <div class="filters">
            <input class="grow" type="text" v-model="query.keyword" @keyup.enter="search"
                   placeholder="搜索报告标题 / 文件名 / 标签 / 摘要 ...">
            <select v-model="query.project_id" @change="search">
              <option :value="null">全部项目</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <select v-model="query.category" @change="search">
              <option value="">全部分类</option>
              <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
            </select>
            <input type="date" v-model="query.date_from" @change="search" title="起始日期">
            <span class="text-light">~</span>
            <input type="date" v-model="query.date_to" @change="search" title="结束日期">
            <button class="btn primary" @click="search">🔍 查询</button>
            <button class="btn" @click="reset">重置</button>
          </div>

          <div class="filters" v-if="selected.length"
               style="background:#ebf4ff;border-bottom:1px solid #bee3f8">
            <span class="fs13"><b>已选 {{ selected.length }} 份报告</b></span>
            <button class="btn sm primary" @click="batchDownload">⬇️ 批量下载</button>
            <button class="btn sm ghost" @click="selected = []">取消选择</button>
          </div>

          <div class="card-body tight">
            <loading v-if="loading"></loading>
            <empty-state v-else-if="!rows.length" icon="📄"
                         text="还没有符合条件的报告"
                         hint="用上方的上传区把第一份报告传上来吧"></empty-state>
            <div class="table-wrap" v-else>
              <table class="data">
                <thead>
                  <tr>
                    <th class="checkbox-cell">
                      <input type="checkbox" :checked="allChecked" @change="toggleAll">
                    </th>
                    <th>报告名称</th><th>所属项目</th><th>分类</th><th>版本</th>
                    <th>报告日期</th><th>上传人</th><th class="num">大小</th>
                    <th class="num">下载</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in rows" :key="r.id" :class="{ selected: selected.indexOf(r.id) >= 0 }">
                    <td class="checkbox-cell">
                      <input type="checkbox" :checked="selected.indexOf(r.id) >= 0"
                             @change="toggleOne(r.id)">
                    </td>
                    <td>
                      <div class="flex-center gap1">
                        <span>{{ iconOf(r.file_ext) }}</span>
                        <div>
                          <div class="strong">{{ r.title }}</div>
                          <div class="fs12 text-light">{{ r.file_name }}</div>
                          <div class="fs12 mt1" v-if="tagList(r.tags).length">
                            <span class="tag outline" v-for="t in tagList(r.tags)" :key="t"
                                  style="margin-right:4px">{{ t }}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span v-if="r.project_name">{{ r.project_name }}</span>
                      <span v-else class="text-light">未关联项目</span>
                    </td>
                    <td><span class="tag blue">{{ r.category }}</span></td>
                    <td>
                      <span class="tag" :class="r.is_latest ? 'green' : 'gray'">v{{ r.version }}</span>
                      <div class="fs12 text-light" v-if="r.is_latest">最新</div>
                      <div class="fs12 link" v-else @click="openVersions(r)">查看历史</div>
                    </td>
                    <td class="fs12">{{ fmt(r.report_date) }}</td>
                    <td class="fs12">{{ r.uploader_name || '—' }}</td>
                    <td class="num fs12">{{ fileSize(r.file_size) }}</td>
                    <td class="num fs12">{{ r.download_count }}</td>
                    <td class="actions">
                      <button class="btn xs" @click="preview(r)" v-if="r.is_previewable">预览</button>
                      <button class="btn xs primary" @click="download(r)">下载</button>
                      <button class="btn xs" @click="openVersions(r)">版本</button>
                      <button class="btn xs" @click="openEdit(r)">编辑</button>
                      <button class="btn xs danger" @click="remove(r)">删除</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <pagination v-if="!loading && rows.length" :page="page" :pages="pages" :total="total"
                      :size="size" @update:page="changePage" @update:size="changeSize"></pagination>
        </div>

        <!-- ================= 版本历史 ================= -->
        <modal v-if="showVersions" :title="'版本历史 — ' + versionTitle"
               :hideFooter="true" @close="showVersions = false">
          <loading v-if="versionLoading" text="读取版本记录 ..."></loading>
          <div class="table-wrap" v-else>
            <table class="data">
              <thead>
                <tr><th>版本</th><th>文件名</th><th>报告日期</th><th>上传人</th>
                  <th class="num">大小</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="v in versions" :key="v.id">
                  <td><span class="tag" :class="v.version === versions[0].version ? 'green' : 'gray'">
                    v{{ v.version }}</span></td>
                  <td class="fs12">{{ v.file_name }}</td>
                  <td class="fs12">{{ fmt(v.report_date) }}</td>
                  <td class="fs12">{{ v.uploader_name || '—' }}</td>
                  <td class="num fs12">{{ fileSize(v.file_size) }}</td>
                  <td class="actions">
                    <button class="btn xs" v-if="v.is_previewable" @click="preview(v)">预览</button>
                    <button class="btn xs primary" @click="download(v)">下载</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="fs12 text-muted mt2">
            版本号按「同项目 + 同标题 + 同分类」自动递增；要发布新版本，用相同标题重新上传即可。
          </div>
        </modal>

        <!-- ================= 编辑元信息 ================= -->
        <modal v-if="showEdit" title="编辑报告信息" :loading="saving"
               @close="showEdit = false" @ok="saveEdit">
          <div class="form-grid c2">
            <div class="form-item full">
              <label>报告标题</label>
              <input type="text" v-model="editForm.title">
            </div>
            <div class="form-item">
              <label>报告分类</label>
              <select v-model="editForm.category">
                <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div class="form-item">
              <label>报告日期</label>
              <input type="date" v-model="editForm.report_date">
            </div>
            <div class="form-item full">
              <label>标签</label>
              <input type="text" v-model="editForm.tags" placeholder="逗号分隔">
            </div>
            <div class="form-item full">
              <label>摘要说明</label>
              <textarea v-model="editForm.summary"></textarea>
            </div>
          </div>
        </modal>
      </div>`,
  };
})();
