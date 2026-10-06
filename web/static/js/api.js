/* ==========================================================================
   API 客户端：统一处理令牌、错误提示、下载
   ========================================================================== */
(function () {
  'use strict';

  const BASE = '/api';
  const TOKEN_KEY = 'cadmin.token';
  const USER_KEY = 'cadmin.user';

  const store = {
    get token() { return localStorage.getItem(TOKEN_KEY) || ''; },
    set token(v) { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); },
    get user() {
      try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
      catch (e) { return null; }
    },
    set user(v) { v ? localStorage.setItem(USER_KEY, JSON.stringify(v)) : localStorage.removeItem(USER_KEY); },
    clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
  };

  /** 把对象拼成 query string，自动丢掉空值 */
  function qs(params) {
    if (!params) return '';
    const parts = [];
    Object.keys(params).forEach(function (k) {
      const v = params[k];
      if (v === undefined || v === null || v === '') return;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  class ApiError extends Error {
    constructor(message, status, payload) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  }

  /** 核心请求方法 */
  async function request(method, path, options) {
    options = options || {};
    const headers = {};
    if (store.token) headers['Authorization'] = 'Bearer ' + store.token;
    let body = options.body;

    if (body !== undefined && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(BASE + path, { method: method, headers: headers, body: body });
    } catch (e) {
      throw new ApiError('网络请求失败，请确认后端服务是否在运行', 0, null);
    }

    if (res.status === 401) {
      store.clear();
      // 同步清掉内存里的用户状态，否则顶栏会残留上一个账号的姓名/角色
      if (window.App && typeof window.App.clearUser === 'function') window.App.clearUser();
      if (!location.hash.startsWith('#/login')) {
        App.toast('登录已过期，请重新登录', 'warning');
        location.hash = '#/login';
      }
      throw new ApiError('未登录或登录已过期', 401, null);
    }

    const isJson = (res.headers.get('content-type') || '').indexOf('application/json') >= 0;
    const payload = isJson ? await res.json().catch(function () { return null; }) : null;

    if (!res.ok) {
      const msg = (payload && payload.message) || ('请求失败（HTTP ' + res.status + '）');
      throw new ApiError(msg, res.status, payload);
    }
    return payload;
  }

  const http = {
    get: function (path, params) { return request('GET', path + qs(params)); },
    post: function (path, body) { return request('POST', path, { body: body }); },
    put: function (path, body) { return request('PUT', path, { body: body }); },
    patch: function (path, body) { return request('PATCH', path, { body: body }); },
    del: function (path, body) { return request('DELETE', path, { body: body }); },
    upload: function (path, formData) { return request('POST', path, { body: formData }); },
  };

  /** 文件下载：带令牌请求，再用 Blob 触发浏览器下载 */
  async function download(path, fallbackName) {
    const res = await fetch(BASE + path, {
      headers: store.token ? { 'Authorization': 'Bearer ' + store.token } : {},
    });
    if (!res.ok) {
      let msg = '下载失败（HTTP ' + res.status + '）';
      try { const j = await res.json(); if (j && j.message) msg = j.message; } catch (e) { /* 忽略 */ }
      throw new ApiError(msg, res.status, null);
    }
    // 优先用后端给的文件名，拿不到就用调用方传的
    let name = fallbackName || 'download';
    const cd = res.headers.get('content-disposition') || '';
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (m) { try { name = decodeURIComponent(m[1]); } catch (e) { /* 忽略 */ } }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
    return name;
  }

  /** 在新标签页打开预览（PDF/图片），同样带令牌 */
  async function openPreview(path) {
    const res = await fetch(BASE + path, {
      headers: store.token ? { 'Authorization': 'Bearer ' + store.token } : {},
    });
    if (!res.ok) {
      let msg = '预览失败（HTTP ' + res.status + '）';
      try { const j = await res.json(); if (j && j.message) msg = j.message; } catch (e) { /* 忽略 */ }
      throw new ApiError(msg, res.status, null);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  window.API = {
    store: store,
    http: http,
    get: http.get,
    post: http.post,
    put: http.put,
    patch: http.patch,
    del: http.del,
    upload: http.upload,
    download: download,
    openPreview: openPreview,
    qs: qs,
    ApiError: ApiError,

    /* ---------------------------------------------------- 各模块接口封装 */
    auth: {
      login: function (username, password) { return http.post('/login', { username: username, password: password }); },
      me: function () { return http.get('/me'); },
      updateMe: function (data) { return http.put('/me', data); },
      changePassword: function (data) { return http.post('/change-password', data); },
      users: function (params) { return http.get('/users', params); },
      createUser: function (data) { return http.post('/users', data); },
      updateUser: function (id, data) { return http.put('/users/' + id, data); },
      resetPassword: function (id, pwd) { return http.post('/users/' + id + '/reset-password', { new_password: pwd }); },
      deleteUser: function (id) { return http.del('/users/' + id); },
    },

    dashboard: {
      overview: function () { return http.get('/dashboard/overview'); },
      orgChart: function () { return http.get('/dashboard/org-chart'); },
    },

    departments: {
      list: function () { return http.get('/departments'); },
      tree: function () { return http.get('/departments/tree'); },
      create: function (data) { return http.post('/departments', data); },
      update: function (id, data) { return http.put('/departments/' + id, data); },
      remove: function (id) { return http.del('/departments/' + id); },
    },

    employees: {
      list: function (params) { return http.get('/employees', params); },
      options: function () { return http.get('/employees/options'); },
      stats: function () { return http.get('/employees/stats'); },
      get: function (id) { return http.get('/employees/' + id); },
      create: function (data) { return http.post('/employees', data); },
      update: function (id, data) { return http.put('/employees/' + id, data); },
      remove: function (id) { return http.del('/employees/' + id); },
      batchStatus: function (ids, status) { return http.post('/employees/batch-status', { ids: ids, status: status }); },
      batchDelete: function (ids) { return http.post('/employees/batch-delete', { ids: ids }); },
      createAccounts: function (ids, password, role) {
        return http.post('/employees/create-accounts', { ids: ids, default_password: password, role: role });
      },
      linkAccount: function (id, userId) { return http.post('/employees/' + id + '/link-account', { user_id: userId }); },
      importFile: function (formData) { return http.upload('/employees/import', formData); },
    },

    projects: {
      list: function (params) { return http.get('/projects', params); },
      options: function () { return http.get('/projects/options'); },
      stats: function () { return http.get('/projects/stats'); },
      get: function (id) { return http.get('/projects/' + id); },
      create: function (data) { return http.post('/projects', data); },
      update: function (id, data) { return http.put('/projects/' + id, data); },
      remove: function (id) { return http.del('/projects/' + id); },
      updateProgress: function (id, progress, remark) {
        return http.patch('/projects/' + id + '/progress', { progress: progress, remark: remark });
      },
      addMembers: function (id, members) { return http.post('/projects/' + id + '/members', { members: members }); },
      removeMember: function (id, memberId) { return http.del('/projects/' + id + '/members/' + memberId); },
    },

    reports: {
      list: function (params) { return http.get('/reports', params); },
      stats: function () { return http.get('/reports/stats'); },
      categories: function () { return http.get('/reports/categories'); },
      get: function (id) { return http.get('/reports/' + id); },
      versions: function (id) { return http.get('/reports/' + id + '/versions'); },
      upload: function (formData) { return http.upload('/reports/upload', formData); },
      update: function (id, data) { return http.put('/reports/' + id, data); },
      remove: function (id) { return http.del('/reports/' + id); },
      download: function (id, name) { return download('/reports/' + id + '/download', name); },
      preview: function (id) { return openPreview('/reports/' + id + '/preview'); },
      batch: function (ids) { return http.post('/reports/batch-download', { ids: ids }); },
    },

    attendance: {
      rules: function () { return http.get('/attendance/rules'); },
      today: function () { return http.get('/attendance/today'); },
      checkIn: function (remark) { return http.post('/attendance/check-in', { remark: remark }); },
      checkOut: function (remark) { return http.post('/attendance/check-out', { remark: remark }); },
      records: function (params) { return http.get('/attendance/records', params); },
      summary: function (params) { return http.get('/attendance/summary', params); },
      save: function (data) { return http.post('/attendance/records', data); },
      remove: function (id) { return http.del('/attendance/records/' + id); },
    },

    leaves: {
      list: function (params) { return http.get('/leaves', params); },
      stats: function (params) { return http.get('/leaves/stats', params); },
      types: function () { return http.get('/leaves/types'); },
      get: function (id) { return http.get('/leaves/' + id); },
      create: function (data) { return http.post('/leaves', data); },
      approve: function (id, action, comment) {
        return http.post('/leaves/' + id + '/approve', { action: action, comment: comment });
      },
      cancel: function (id) { return http.post('/leaves/' + id + '/cancel'); },
      remove: function (id) { return http.del('/leaves/' + id); },
    },

    announcements: {
      list: function (params) { return http.get('/announcements', params); },
      get: function (id) { return http.get('/announcements/' + id); },
      create: function (data) { return http.post('/announcements', data); },
      update: function (id, data) { return http.put('/announcements/' + id, data); },
      patch: function (id, data) { return http.patch('/announcements/' + id, data); },
      remove: function (id) { return http.del('/announcements/' + id); },
    },

    logs: {
      list: function (params) { return http.get('/logs', params); },
      stats: function (days) { return http.get('/logs/stats', { days: days }); },
      mine: function (params) { return http.get('/logs/mine', params); },
    },
  };
})();
