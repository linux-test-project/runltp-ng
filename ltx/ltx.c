#include <linux/limits.h>
#define _GNU_SOURCE

#include <endian.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <poll.h>
#include <signal.h>
#include <time.h>
#include <limits.h>

#ifdef __GLIBC__
#include <execinfo.h>
#endif

#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/uio.h>
#include <sys/epoll.h>
#include <sys/signalfd.h>
#include <sys/sendfile.h>

#include "errnos.h"

#define VERSION "0.0.1-dev"

#define LTX_POS ((struct ltx_pos){ __FILE__, __func__, __LINE__ })
#define LTX_LOG(fmt, ...) ltx_log(LTX_POS, fmt, ##__VA_ARGS__)

#ifdef __GLIBC__
#define PRINT_BACKTRACE do { \
	void *buf[BUFSIZ];						\
	int i, nptrs = backtrace(buf, BUFSIZ);				\
	for (i = 0; i < nptrs; i++)					\
		fprintf(stderr, "\t%p\n", buf[i]);			\
} while(0);
#else
#define PRINT_BACKTRACE do {} while(0);
#endif

#define ltx_assert(expr, fmt, ...) do {					\
	if (expr)							\
		break;							\
									\
	ltx_log(LTX_POS,						\
		"Fatal assertion '" #expr "': " fmt,			\
		##__VA_ARGS__);						\
									\
	PRINT_BACKTRACE							\
	exit(1);							\
} while (0);

#define LTX_EXP_FD(expr)			\
	ltx_exp_fd(LTX_POS, expr, #expr)
#define LTX_EXP_0(expr)				\
	ltx_exp_0(LTX_POS, expr, #expr)
#define LTX_EXP_POS(expr)			\
	ltx_exp_pos(LTX_POS, expr, #expr)

struct ltx_pos {
	const char *const file;
	const char *const func;
	const int line;
};

struct ltx_buf {
	size_t off;
	size_t used;
	uint8_t data[BUFSIZ];
};

struct ltx_cursor {
	uint8_t *start;
	size_t used;
	size_t left;
};

struct ltx_str {
	size_t len;
	char *const data;
};

enum ltx_msg_types {
	ltx_msg_ping,
	ltx_msg_pong,
	ltx_msg_env,
	ltx_msg_exec,
	ltx_msg_log,
	ltx_msg_result,
	ltx_msg_get_file,
	ltx_msg_set_file,
	ltx_msg_data,
	ltx_msg_kill,
	ltx_msg_version,
	ltx_msg_max = ltx_msg_version,
};

enum ltx_kind {
	ltx_array = ltx_msg_max + 1,
	ltx_number,
	ltx_str,
	ltx_bin,
	ltx_nil,
	ltx_end
};

enum ltx_num_kind {
	ltx_array_size = ltx_array,
	ltx_ind_num = ltx_number,
	ltx_str_size = ltx_str,
	ltx_bin_size = ltx_bin,
};

struct ltx_obj {
	enum ltx_kind kind;
	union {
		struct ltx_str str;
		uint64_t u64;
	};
};

#define LTX_NUMBER(n) { .kind = ltx_number, .u64 = n }
#define LTX_NIL { .kind = ltx_nil, .u64 = 0 }
#define LTX_BIN(l, d) { .kind = ltx_bin, .str = { .len = l, .data = d } }
#define LTX_STR(l, d) { .kind = ltx_str, .str = { .len = l, .data = d } }
#define LTX_END { .kind = ltx_end, .u64 = 0 }
#define LTX_WRITE_MSG(b, t, ...)		 \
	ltx_write_msg(b, t, (struct ltx_obj[]){ \
			__VA_ARGS__		 \
			, LTX_END		 \
	})

enum msgp_fmt {
	msgp_fixint0 = 0x00,
	msgp_fixing127 = 0x7f,
	msgp_fixarray0 = 0x90,
	msgp_fixarray15 = 0x9f,
	msgp_fixstr0 = 0xa0,
	msgp_fixstr31 = 0xbf,
	msgp_nil = 0xc0,
	msgp_bin8 = 0xc4,
	msgp_bin16 = 0xc5,
	msgp_bin32 = 0xc6,
	msgp_uint8 = 0xcc,
	msgp_uint16 = 0xcd,
	msgp_uint32 = 0xce,
	msgp_uint64 = 0xcf,
	msgp_str8 = 0xd9,
	msgp_str16 = 0xda,
	msgp_str32 = 0xdb,
	msgp_array16 = 0xdc
};

enum ltx_ev_source_type {
	ltx_ev_io,
	ltx_ev_child_io,
	ltx_ev_signal
};

struct ltx_ev_source {
	enum ltx_ev_source_type type;
	union {
		uint8_t table_id;
		int fd;
	};
};

struct ltx_child {
	struct ltx_ev_source ev_source;
	pid_t pid;
	int fd;
	char args[ARG_MAX/2];
	char env_ks[ARG_MAX/16];
	uint16_t env_ksv[256];
	char env_vs[ARG_MAX/2];
	uint16_t env_vsv[256];
};

static struct ltx_ev_source ltx_in = {
	.type = ltx_ev_io,
	.fd = STDIN_FILENO,
};
static struct ltx_buf in_buf;

static struct ltx_ev_source ltx_out = {
	.type = ltx_ev_io,
	.fd = STDOUT_FILENO,
};
static int out_fd_blocked;
static struct ltx_buf out_buf;

static struct ltx_ev_source ltx_sig = {
	.type = ltx_ev_signal
};
static int ep_fd;
static pid_t ltx_pid;

static struct ltx_child childs[0x7f];
static uint32_t child_pids[0x7f];

__attribute__((const, warn_unused_result))
static size_t ltx_min_sz(const size_t a, const size_t b)
{
	return a < b ? a : b;
}

__attribute__((const, warn_unused_result))
static size_t ltx_max_sz(const size_t a, const size_t b)
{
	return a > b ? a : b;
}

__attribute__((pure, nonnull, warn_unused_result))
static uint8_t *ltx_buf_start(struct ltx_buf *const self)
{
	return self->data + self->off;
}

__attribute__((pure, nonnull, warn_unused_result))
static uint8_t *ltx_buf_end(struct ltx_buf *const self)
{
	return ltx_buf_start(self) + self->used;
}

__attribute__((nonnull))
static void ltx_buf_push(struct ltx_buf *const self, uint8_t v)
{
	ltx_buf_end(self)[0] = v;
	self->used++;
}

__attribute__((pure, nonnull, warn_unused_result))
static size_t ltx_buf_avail(const struct ltx_buf *const self)
{
	return BUFSIZ - (self->off + self->used);
}

__attribute__((nonnull, warn_unused_result))
static uint8_t *ltx_cur_take(struct ltx_cursor *const self, size_t len)
{
	uint8_t *ptr = self->start + self->used;

	self->left -= len;
	self->used += len;

	return ptr;
}

__attribute__((nonnull, warn_unused_result))
static uint8_t ltx_cur_shift(struct ltx_cursor *const self)
{
	return ltx_cur_take(self, 1)[0];
}

__attribute__((nonnull))
static void ltx_write_number(struct ltx_buf *const buf,
			     enum ltx_num_kind kind,
			     const uint64_t n)
{
	uint8_t h = 0;
	size_t l = 0;

	switch (kind) {
	case ltx_array:
		if (n > 15) {
			l = 2;
			h = msgp_array16;
		} else {
			h = msgp_fixarray0 + n;
		}
		break;
	case ltx_number:
		if ((~0ULL << 32) & n) {
			l = 8;
			h = msgp_uint64;
		} else if (0xffff0000 & n) {
			l = 4;
			h = msgp_uint32;
		} else if (0xff00 & n) {
			l = 2;
			h = msgp_uint16;
		} else if (0x80 & n) {
			l = 1;
			h = msgp_uint8;
		} else {
			h = n;
		}
		break;
	case ltx_str:
		if (0xffff0000 & n) {
			l = 4;
			h = msgp_str32;
		} else if (0xff00 & n) {
			l = 2;
			h = msgp_str16;
		} else if (n > 31) {
			l = 1;
			h = msgp_str8;
		} else {
			h = msgp_fixstr0 + n;
		}
		break;
	case ltx_bin:
		if (0xffff0000 & n) {
			l = 4;
			h = msgp_bin32;
		} else if (0xff00 & n) {
			l = 2;
			h = msgp_bin16;
		} else {
			l = 1;
			h = msgp_bin8;
		}
		break;
	}

	ltx_buf_push(buf, h);
	for (unsigned j = 9 - l; j < 9; j++)
		ltx_buf_push(buf, (uint8_t)(n >> (64 - 8*j)));
}

__attribute__((nonnull))
static void ltx_fmt(const struct ltx_pos pos,
		    struct ltx_buf *const buf,
		    const char *const fmt,
		    va_list ap)
{
	buf->used += snprintf((char *)ltx_buf_end(buf), ltx_buf_avail(buf) - 2,
			      "[%s:%s:%i] ", pos.file, pos.func, pos.line);
	buf->used += vsnprintf((char *)ltx_buf_end(buf), ltx_buf_avail(buf) - 2, fmt, ap);

	memcpy(ltx_buf_end(buf), "\n\0", 2);
	buf->used++;
}

static void ltx_write_obj(struct ltx_buf *const buf,
			  const struct ltx_obj *const obj)
{
	switch (obj->kind) {
	case ltx_number:
		ltx_write_number(buf, ltx_ind_num, obj->u64);
		break;
	case ltx_str:
	case ltx_bin:
		ltx_write_number(buf,
				 (enum ltx_num_kind)obj->kind, obj->str.len);

		if (!obj->str.data)
			break;

		memmove(ltx_buf_end(buf), obj->str.data, obj->str.len);
		buf->used += obj->str.len;
		break;
	case ltx_nil:
		ltx_buf_push(buf, msgp_nil);
		break;
	case ltx_array:
	case ltx_end:
		__builtin_unreachable();
	}
}

__attribute__((nonnull))
static void ltx_write_msg(struct ltx_buf *const buf,
			  enum ltx_msg_types msg_type,
			  struct ltx_obj *objs)
{
	size_t len = 1;

	for (struct ltx_obj *obj = objs; obj->kind != ltx_end; obj++)
		len++;

	ltx_write_number(buf, ltx_array_size, len);
	ltx_buf_push(buf, msg_type);

	for (struct ltx_obj *obj = objs; obj->kind != ltx_end; obj++)
		ltx_write_obj(buf, obj);
}

__attribute__((warn_unused_result))
static uint64_t ltx_gettime(void)
{
	struct timespec ts;

#ifdef CLOCK_MONOTONIC_RAW
	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
#else
	clock_gettime(CLOCK_MONOTONIC, &ts);
#endif

	return ts.tv_sec * 1000000000 + ts.tv_nsec;
}

__attribute__((nonnull, format(printf, 2, 3)))
static void ltx_log(const struct ltx_pos pos, const char *const fmt, ...)
{
	struct ltx_buf msg = { .off = 32, .used = 0 };
	va_list ap;
	ssize_t res;
	const uint8_t *text = ltx_buf_start(&msg);
	size_t len;

	va_start(ap, fmt);
	ltx_fmt(pos, &msg, fmt, ap);
	va_end(ap);

	res = write(STDERR_FILENO, text, msg.used);

	if (ltx_pid != getpid())
		return;

	msg.off = 0;
	len = msg.used;
	msg.used = 0;
	LTX_WRITE_MSG(&msg, ltx_msg_log,
		      LTX_NIL,
		      LTX_NUMBER(ltx_gettime()),
		      LTX_STR(len, (char *)text));

	while (msg.used) {
		res = write(ltx_out.fd, ltx_buf_start(&msg), msg.used);
		if (res < 0)
			break;

		msg.off += res;
		msg.used -= res;
	}
}

__attribute__((nonnull, warn_unused_result))
static int ltx_exp_fd(const struct ltx_pos pos,
		      const int fd,
		      const char *const expr)
{
	if (fd > -1)
		return fd;

	ltx_log(pos, "Invalid FD: %s = %d: %s", expr, fd, ltx_strerrno(errno));

	exit(1);
}

__attribute__((nonnull))
static void ltx_exp_0(const struct ltx_pos pos,
		      const int ret,
		      const char *const expr)
{
	if (!ret)
		return;

	ltx_log(pos, "Not Zero: %s = %d: %s", expr, ret, ltx_strerrno(errno));

	exit(1);
}

__attribute__((nonnull))
static int ltx_exp_pos(const struct ltx_pos pos,
		       const int ret,
		       const char *const expr)
{
	if (ret > -1)
		return ret;

	ltx_log(pos, "Not positive: %s = %d: %s", expr, ret, ltx_strerrno(errno));

	exit(1);
}

static void ltx_epoll_add(struct ltx_ev_source *ev_src,
			  const uint32_t events)
{
	struct epoll_event ev = {
		.events = events,
		.data = (epoll_data_t){ .ptr = ev_src },
	};
	const int fd = ev_src->type == ltx_ev_child_io ?
		childs[ev_src->table_id].fd :
		ev_src->fd;

	LTX_EXP_0(epoll_ctl(ep_fd, EPOLL_CTL_ADD, fd, &ev));
}

static void fill_read_buf(void)
{
	ltx_assert(ltx_buf_avail(&in_buf) > 0, "read buffer full");

	const int ilen = LTX_EXP_POS(read(ltx_in.fd,
					  ltx_buf_end(&in_buf),
					  ltx_buf_avail(&in_buf)));
	in_buf.used += ilen;
}

static void drain_write_buf(void)
{
	while (out_buf.used) {
		const int olen = write(ltx_out.fd, ltx_buf_start(&out_buf), out_buf.used);

		if (olen < 0 && errno == EAGAIN) {
			out_fd_blocked = 1;
			break;
		}

		ltx_assert(olen > -1,
			   "write(out_fd, out_buf.data, %zu): %s",
			   out_buf.used, ltx_strerrno(errno));

		out_buf.off += olen;
		out_buf.used -= olen;
	}

	if (out_buf.used) {
		memmove(out_buf.data,
			ltx_buf_start(&out_buf),
			out_buf.used);
	}

	out_buf.off = 0;
}

__attribute__((nonnull, warn_unused_result))
static size_t ltx_read_size(struct ltx_cursor *const cur, const size_t len)
{
	uint8_t *d = ltx_cur_take(cur, len);
	size_t res = 0;

	for (unsigned i = 0; i < len; i++) {
		res <<= i * 8;
		res += d[i];
	}

	return res;
}

__attribute__((nonnull, warn_unused_result))
static ssize_t ltx_read_str_size(struct ltx_cursor *const cur)
{
	const enum msgp_fmt fmt = ltx_cur_shift(cur);
	size_t w;

	switch (fmt) {
	case msgp_fixstr0 ... msgp_fixstr31:
		return fmt - msgp_fixstr0;
	case msgp_str8 ... msgp_str32:
		w = 1 + fmt - msgp_str8;
		break;
	case msgp_bin8 ... msgp_bin32:
		w = 1 + fmt - msgp_bin8;
		break;
	default:
		ltx_assert(0, "Not a string fmt: '%x'", fmt);
	}

	if (w > cur->left)
		return -1;

	return ltx_read_size(cur, w);
}

__attribute__((nonnull, warn_unused_result))
static struct ltx_str ltx_read_str(struct ltx_cursor *cur)
{
	const ssize_t l = ltx_read_str_size(cur);

	if (l == -1 || (size_t)l > cur->left) {
		return (struct ltx_str) {
			.len = 0,
			.data = NULL,
		};
	}

	return (struct ltx_str) {
		.len = l,
		.data = (char *)ltx_cur_take(cur, l)
	};
}

static void ltx_to_cstring(struct ltx_str *str, char *cstr)
{
	memcpy(cstr, str->data, str->len);
	cstr[str->len] = '\0';
}

static void ltx_msg_echo(struct ltx_cursor *cur)
{
	ltx_assert(ltx_buf_avail(&out_buf) > cur->used,
		   "Out buffer full: %zu < %zu",
		   ltx_buf_avail(&out_buf), cur->used);

	memcpy(ltx_buf_end(&out_buf), cur->start, cur->used);
	out_buf.used += cur->used;
}

static int process_exec_msg(struct ltx_cursor *cur, const uint8_t args_n)
{
	uint8_t table_id;
	char *argsv[256];
	pid_t pid;
	struct ltx_child *child;
	int c, pipefd[2];

	table_id = ltx_cur_shift(cur);
	ltx_assert(table_id < 0x7f, "Exec: (table_id = %u) > 127", table_id);
	ltx_assert(args_n - 1 < 256, "Exec: Too many arguments: %u", args_n);

	if (!cur->left)
		return 0;

	child = childs + table_id;
	argsv[0] = child->args;
	for (c = 0; c < args_n - 1; c++) {
		struct ltx_str path = ltx_read_str(cur);

		if (!path.data)
			return 0;

		ltx_to_cstring(&path, argsv[c]);
		argsv[c + 1] = argsv[c] + path.len + 1;
	}
	argsv[c] = NULL;

	ltx_msg_echo(cur);

	LTX_EXP_0(pipe2(pipefd, O_CLOEXEC));
	child->fd = pipefd[0];
	ltx_epoll_add(&child->ev_source, EPOLLOUT);
	pid = LTX_EXP_POS(fork());

	if (pid) {
		close(pipefd[1]);
		childs[table_id].pid = pid;
		child_pids[table_id] = pid;
		return 1;
	}

	for (int i = 0; i < 256; i++) {
		const char *const key = child->env_ks + child->env_ksv[i];
		const char *const val = child->env_vs + child->env_vsv[i];

		if (!child->env_ksv[i + 1])
			break;

		LTX_EXP_0(setenv(key, val, 1));
	}

	LTX_EXP_POS(dup2(pipefd[1], STDERR_FILENO));
	LTX_EXP_POS(dup2(pipefd[1], STDOUT_FILENO));

	LTX_EXP_0(execv(argsv[0], argsv));
	__builtin_unreachable();
}

static int process_get_file_msg(struct ltx_cursor *cur)
{
	struct ltx_str path = ltx_read_str(cur);
	struct stat st;
	char cpath[PATH_MAX];
	int fd;

	if (path.data == NULL)
		return 0;

	ltx_msg_echo(cur);

	ltx_to_cstring(&path, cpath);
	fd = LTX_EXP_FD(open(cpath, O_RDONLY));
	LTX_EXP_0(fstat(fd, &st));

	ltx_assert(st.st_size < 0x7ffff000,
		   "%s: too large (%ld)", cpath, st.st_size);

	LTX_WRITE_MSG(&out_buf, ltx_msg_data, LTX_BIN(st.st_size, NULL));

	fcntl(ltx_out.fd, F_SETFL, 0);
	drain_write_buf();
	const ssize_t len = LTX_EXP_POS(sendfile(ltx_out.fd, fd, NULL, 0x7ffff000));
	fcntl(ltx_out.fd, F_SETFL, O_NONBLOCK);

	ltx_assert(len == st.st_size, "(len = %zd) != (st.st_size = %ld)",
		   len, st.st_size);

	return 1;
}

static int process_set_file_msg(struct ltx_cursor *cur)
{
	struct ltx_str path = ltx_read_str(cur);
	char cpath[PATH_MAX];
	int fd;
	ssize_t bin_len, left, len;
	off_t zero = 0;

	if (path.data == NULL || !cur->left)
		return 0;

	bin_len = ltx_read_str_size(cur);

	if (bin_len == -1)
		return 0;

	ltx_to_cstring(&path, cpath);
	fd = LTX_EXP_FD(open(cpath, O_RDWR | O_CREAT | O_TRUNC, 0600));

	left = bin_len;
	while (cur->left && left) {
		len = LTX_EXP_POS(write(fd, cur->start + cur->used,
					ltx_min_sz(cur->left, bin_len)));
		left -= len;
		cur->left -= len;
		cur->used += len;
	}

	if (!left)
		goto echo;

	while (left) {
		len = LTX_EXP_POS(splice(ltx_in.fd, NULL, fd, NULL, left, 0));

		if (!len)
			break;

		left -= len;
	}

echo:
	LTX_WRITE_MSG(&out_buf, ltx_msg_set_file,
		      { .kind = ltx_str, .str = path },
		      LTX_BIN(bin_len, NULL));
	fcntl(ltx_out.fd, F_SETFL, 0);
	drain_write_buf();
	len = LTX_EXP_POS(sendfile(ltx_out.fd, fd, &zero, bin_len));
	fcntl(ltx_out.fd, F_SETFL, O_NONBLOCK);

	close(fd);
	return 1;
}

static void process_kill_msg(struct ltx_cursor *const cur)
{
	int ret = 0;
	const uint8_t table_id = ltx_cur_shift(cur);

	ltx_assert(table_id < 0x7f, "Kill: (table_id = %u) > 127", table_id);

	ltx_msg_echo(cur);

	if (child_pids[table_id])
		ret = kill(child_pids[table_id], SIGKILL);
	LTX_EXP_0(ret * (errno != ESRCH));
}

static int process_env_msg(struct ltx_cursor *const cur)
{
	int i;
	const uint8_t table_id = ltx_cur_shift(cur);
	if (!cur->left)
		return 0;
	ltx_assert(table_id == msgp_nil || table_id < 128,
		   "Env: table_id=%u", table_id);

	char ckey[256];
	struct ltx_str key = ltx_read_str(cur);
	if (!key.data)
		return 0;
	ltx_assert(key.len && key.len < 256, "Env: key.len=%zu", key.len);

	char cval[PATH_MAX];
	struct ltx_str val = ltx_read_str(cur);
	if (!val.data)
		return 0;
	ltx_assert(val.len < PATH_MAX, "Env: val.len=%zu", val.len);

	ltx_msg_echo(cur);

	if (table_id == msgp_nil) {
		ltx_to_cstring(&key, ckey);
		ltx_to_cstring(&val, cval);
		LTX_EXP_0(setenv(ckey, cval, 1));
		return 1;
	}

	struct ltx_child *child = childs + table_id;
	for (i = 0; i < 256; i++) {
		size_t cur_off = child->env_ksv[i];
		size_t nxt_off = child->env_ksv[i + 1];
		size_t new_off = cur_off + key.len + 1;
		size_t cur_len = nxt_off ? nxt_off - cur_off : 0;
		char *cur = child->env_ks + cur_off;

		if (!cur_len) {
			memcpy(cur, key.data, key.len);
			cur[key.len] = '\0';
			ltx_assert(new_off < ARG_MAX/16,
				   "Ran out of env key space: %zu", new_off);
			child->env_ksv[i + 1] = new_off;
			break;
		}

		if (key.len + 1 == cur_len && !memcmp(cur, key.data, key.len))
			break;
	}

	ltx_assert(i < 255, "Ran out of env slots in %u", table_id);

	size_t cur_off = child->env_vsv[i];
	size_t nxt_off = child->env_vsv[i + 1];
	size_t new_off = cur_off + val.len + 1;
	size_t slot_len = nxt_off ? nxt_off - cur_off : 0;

	ltx_assert(new_off < ARG_MAX/2,
		   "Ran out of env value space: %zu", new_off);

	if (slot_len && slot_len != val.len + 1) {
		memmove(child->env_vs + new_off,
			child->env_vs + nxt_off,
			ARG_MAX/2 - ltx_max_sz(nxt_off, new_off));
	}

	child->env_vsv[i + 1] = new_off;
	ltx_to_cstring(&val, child->env_vs + cur_off);

	return 1;
}

static void process_msgs(void)
{
	struct ltx_cursor outer_cur = {
		.start = ltx_buf_start(&in_buf),
		.left = in_buf.used,
		.used = 0
	};

	while (outer_cur.left > 1) {
		struct ltx_cursor cur = {
			.start = outer_cur.start + outer_cur.used,
			.left = outer_cur.left,
			.used = 0,
		};
		enum msgp_fmt msg_fmt = ltx_cur_shift(&cur);

		ltx_assert(msg_fmt & msgp_fixarray0,
			   "Message should start with fixarray, not 0x%x",
			   msg_fmt);

		const uint8_t msg_arr_len = msg_fmt - msgp_fixarray0;
		const uint8_t msg_type = ltx_cur_shift(&cur);

		ltx_assert(msg_type <= ltx_msg_max,
			   "(msg_type = %u) > ltx_msg_max",
			   msg_type);

		switch (msg_type) {
		case ltx_msg_ping:
			ltx_assert(msg_arr_len == 1,
				   "Ping: (msg_arr_len = %u) != 1",
				   msg_arr_len);

			ltx_msg_echo(&cur);
			LTX_WRITE_MSG(&out_buf, ltx_msg_pong,
				      LTX_NUMBER(ltx_gettime()));
			break;
		case ltx_msg_pong:
			ltx_assert(!ltx_msg_pong, "Not handled by executor");
		case ltx_msg_env:
			ltx_assert(msg_arr_len == 4,
				   "Env: (msg_arr_len = %u) != 4",
				   msg_arr_len);

			if (!cur.left)
				goto out;

			if (!process_env_msg(&cur))
				goto out;
			break;
		case ltx_msg_exec:
			ltx_assert(msg_arr_len > 2,
				   "Exec: (msg_arr_len = %u) < 3",
				   msg_arr_len);

			if (!cur.left)
				goto out;

			if (!process_exec_msg(&cur, msg_arr_len - 1))
				goto out;

			break;
		case ltx_msg_log:
			ltx_assert(!ltx_msg_log, "Not handled by executor");
		case ltx_msg_result:
			ltx_assert(!ltx_msg_result, "Not handled by executor");
		case ltx_msg_get_file:
			ltx_assert(msg_arr_len == 2,
				   "Get File: (msg_arr_len = %u) != 2",
				   msg_arr_len);

			if (!cur.left)
				goto out;

			if (!process_get_file_msg(&cur))
				goto out;
			break;
		case ltx_msg_set_file:
			ltx_assert(msg_arr_len == 3,
				   "Set File: (msg_arr_len = %u) != 3",
				   msg_arr_len);

			if (!cur.left)
				goto out;

			if (!process_set_file_msg(&cur))
				goto out;
			break;
		case ltx_msg_data:
			ltx_assert(!ltx_msg_data, "Not handled by executor");
		case ltx_msg_kill:
			ltx_assert(msg_arr_len == 2,
				   "Kill: (msg_arr_len = %u) != 2",
				   msg_arr_len);

			if (!cur.left)
				goto out;

			process_kill_msg(&cur);
			break;
		case ltx_msg_version:
			ltx_assert(msg_arr_len == 1,
				   "Version: (msg_arr_len = %u) != 1",
				   msg_arr_len);

			ltx_msg_echo(&cur);
			LTX_WRITE_MSG(&out_buf, ltx_msg_log,
				      LTX_NIL,
				      LTX_NUMBER(ltx_gettime()),
				      LTX_STR(sizeof("LTX Version="VERSION),
					      "LTX Version="VERSION));
			break;
		}

		if (out_buf.used > BUFSIZ / 4)
			drain_write_buf();

		outer_cur.used += cur.used;
		outer_cur.left = cur.left;
	}
out:
	in_buf.used = outer_cur.left;
	memmove(outer_cur.start,
		outer_cur.start + outer_cur.used,
		outer_cur.left);
}

static int process_event(const struct epoll_event *const ev)
{
	struct ltx_ev_source *const ev_src = ev->data.ptr;
	struct ltx_child *child;
	struct signalfd_siginfo si[0x7f];
	ssize_t len, sig_n;
	uint8_t table_id;
	uint8_t *log_text;

	switch (ev_src->type) {
	case ltx_ev_io:
		if (ev->events & EPOLLIN)
			fill_read_buf();

		if (ev->events & EPOLLOUT)
			out_fd_blocked = 0;

		if (ev->events & EPOLLHUP)
			return 1;

		return 0;
	case ltx_ev_signal:
		len = LTX_EXP_POS(read(ev_src->fd, si, sizeof(si[0]) * 0x7f));
		sig_n = len / sizeof(si[0]);

		ltx_assert(sig_n * (ssize_t)sizeof(si[0]) == len,
			   "signalfd reads not atomic?");

		for (int i = 0; i < sig_n; i++) {
			for (table_id = 0; table_id < 0x7f; table_id++) {
				if (child_pids[table_id] == si[i].ssi_pid)
					break;
			}

			ltx_assert(table_id < 0x7f,
				   "PID not found: %d", si[i].ssi_pid);

			LTX_WRITE_MSG(&out_buf, ltx_msg_result,
				       LTX_NUMBER(table_id),
				       LTX_NUMBER(ltx_gettime()),
				       LTX_NUMBER(si[i].ssi_code),
				       LTX_NUMBER(si[i].ssi_status));

			child_pids[table_id] = 0;
			childs[table_id].pid = 0;
		}
		break;
	case ltx_ev_child_io:
		ltx_assert(ev->events & EPOLLHUP || ev->events & EPOLLOUT,
			   "Unexpected child IO event: 0x%x", ev->events);

		child = childs + ev_src->table_id;
		log_text = ltx_buf_end(&out_buf) + 32;
		len = LTX_EXP_POS(read(child->fd,
				       log_text,
				       ltx_min_sz(1024, ltx_buf_avail(&out_buf) - 32)));

		if (len) {
			LTX_WRITE_MSG(&out_buf, ltx_msg_log,
				      LTX_NUMBER(ev_src->table_id),
				      LTX_NUMBER(ltx_gettime()),
				      LTX_STR(len, (char *)log_text));
		} else {
			close(child->fd);
		}
	}

	if (out_buf.used > BUFSIZ / 4)
		drain_write_buf();

	return 0;
}

static void event_loop(void)
{
	const int maxevents = 128;
	int stop = 0;
	struct epoll_event events[maxevents];
	sigset_t mask;

	sigemptyset(&mask);
	sigaddset(&mask, SIGCHLD);
	LTX_EXP_0(sigprocmask(SIG_BLOCK, &mask, NULL));
	ltx_sig.fd = LTX_EXP_FD(signalfd(-1, &mask, SFD_CLOEXEC));

	fcntl(ltx_out.fd, F_SETFL, O_NONBLOCK);

	ep_fd = LTX_EXP_FD(epoll_create1(EPOLL_CLOEXEC));

	ltx_epoll_add(&ltx_in, EPOLLIN);
	ltx_epoll_add(&ltx_out, EPOLLOUT | EPOLLET);
	ltx_epoll_add(&ltx_sig, EPOLLIN);

	while (!stop) {
		const int eventsn =
			LTX_EXP_POS(epoll_wait(ep_fd, events, maxevents, 100));

		for (int i = 0; i < eventsn; i++)
			stop += process_event(events + i);

		if (out_buf.used && !out_fd_blocked)
			drain_write_buf();

		if (in_buf.used < 2)
			continue;

		process_msgs();

		if (out_buf.used && !out_fd_blocked)
			drain_write_buf();
	}
}

int main(void)
{
	ltx_pid = getpid();

	for (int i = 0; i < 0x7f; i++) {
		struct ltx_ev_source *const evs = &childs[i].ev_source;

		evs->type = ltx_ev_child_io;
		evs->table_id = i;
	}

	event_loop();

	LTX_LOG("Exiting");
	return 0;
}
