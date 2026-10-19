/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 zig-syscall-lt contributors.
 * Independently reconstructed from public lecture specifications.
 * NOT Michael Kerrisk's altio_speed.c. No TLPI source is copied here.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/resource.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static void fail(const char *s) {
  perror(s);
  exit(1);
}
static void require(int ok, const char *s) {
  if (!ok) {
    fprintf(stderr, "invariant: %s\n", s);
    exit(2);
  }
}
static uint64_t now(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t))
    fail("clock");
  return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
static uint64_t random64(uint64_t *s) {
  *s ^= *s << 13;
  *s ^= *s >> 7;
  *s ^= *s << 17;
  return *s;
}
static uint64_t us(struct timeval t) {
  return (uint64_t)t.tv_sec * 1000000 + t.tv_usec;
}
int main(int argc, char **argv) {
  if (argc != 13) {
    fprintf(stderr, "backend kind N ready loops timeout capacity placement "
                    "layout work changes seed\n");
    return 2;
  }
  const char *backend = argv[1], *kind = argv[2], *placement = argv[8],
             *layout = argv[9], *work = argv[10];
  int n = atoi(argv[3]), r = atoi(argv[4]), timeout = atoi(argv[6]),
      cap = atoi(argv[7]), changes = atoi(argv[11]);
  uint64_t loops = strtoull(argv[5], 0, 10), seed = strtoull(argv[12], 0, 10);
  if (!seed)
    seed = 1;
  int ep = !strcmp(backend, "epoll"), po = !strcmp(backend, "poll"),
      se = !strcmp(backend, "select");
  require((ep || po || se) && n > 0 && r >= 0 && r <= n && cap > 0 &&
              loops > 0 && (timeout == 0 || timeout == -1),
          "arguments");
  require(timeout == 0 || r > 0, "infinite wait requires ready fd");
  require(changes >= 0 && changes <= n && (!changes || ep), "changes");
  require(!strcmp(kind, "pipe") || !strcmp(kind, "socket"), "kind");
  require(!strcmp(layout, "contiguous") || !strcmp(layout, "normal"), "layout");
  int full = !strcmp(work, "full"), api = !strcmp(work, "api"),
      scan_only = !strcmp(work, "scan-only"),
      verify_only = !strcmp(work, "verify-only"),
      ctl_only = !strcmp(work, "ctl-only");
  require(api || full || scan_only || verify_only || ctl_only ||
              !strcmp(work, "scan") || !strcmp(work, "verify"),
          "work");
  require((!full || r > 0) && (!ctl_only || ep), "work prerequisites");
  int (*pairs)[2] = calloc(n, sizeof(*pairs));
  int *order = calloc(n, sizeof(int)), *indices = calloc(n, sizeof(int));
  unsigned char *expected = calloc(n, 1), *seen = calloc(n, 1);
  struct pollfd *fds = calloc(n, sizeof(*fds));
  struct epoll_event *events = calloc(cap, sizeof(*events));
  require(pairs && order && indices && expected && seen && fds && events,
          "allocation");
  for (int i = 0; i < n; i++) {
    if (!strcmp(kind, "pipe")) {
      if (pipe(pairs[i]))
        fail("pipe");
    } else if (socketpair(AF_UNIX, SOCK_STREAM, 0, pairs[i]))
      fail("socketpair");
    order[i] = i;
  }
  if (!strcmp(layout, "contiguous")) {
    for (int i = 0; i < n; i++)
      for (int j = 0; j < 2; j++) {
        int d = fcntl(pairs[i][j], F_DUPFD_CLOEXEC, 2 * n + 32);
        if (d < 0)
          fail("fcntl");
        close(pairs[i][j]);
        pairs[i][j] = d;
      }
    for (int i = 0; i < n; i++) {
      if (dup2(pairs[i][0], 3 + i) < 0)
        fail("dup2");
      close(pairs[i][0]);
      pairs[i][0] = 3 + i;
    }
  }
  if (!strcmp(placement, "random")) {
    for (int i = n - 1; i > 0; i--) {
      int j = random64(&seed) % (i + 1), t = order[i];
      order[i] = order[j];
      order[j] = t;
    }
  } else if (!strcmp(placement, "middle")) {
    require(r == 1, "middle ready=1");
    order[0] = n / 2;
  } else if (!strcmp(placement, "last")) {
    require(r == 1, "last ready=1");
    order[0] = n - 1;
  } else
    require(!strcmp(placement, "first"), "placement");
  for (int i = 0; i < r; i++) {
    expected[order[i]] = 1;
    ssize_t nr;
    do {
      nr = write(pairs[order[i]][1], "x", 1);
    } while (nr < 0 && errno == EINTR);
    if (nr != 1)
      fail("write");
  }
  fd_set master, readyset;
  FD_ZERO(&master);
  int maxfd = 0;
  for (int i = 0; i < n; i++) {
    fds[i] = (struct pollfd){.fd = pairs[i][0], .events = POLLIN};
    if (pairs[i][0] > maxfd)
      maxfd = pairs[i][0];
    if (se) {
      require(pairs[i][0] < FD_SETSIZE, "FD_SETSIZE");
      FD_SET(pairs[i][0], &master);
    }
  }
  int epfd = -1;
  uint64_t setup = now();
  if (ep) {
    epfd = epoll_create1(EPOLL_CLOEXEC);
    if (epfd < 0)
      fail("epoll_create1");
    for (int i = 0; i < n; i++) {
      struct epoll_event ev = {.events = EPOLLIN, .data.u64 = i};
      if (epoll_ctl(epfd, EPOLL_CTL_ADD, pairs[i][0], &ev))
        fail("epoll_ctl ADD");
    }
  }
  setup = now() - setup;
  uint64_t calls = 0, observed = 0, checksum = 0, controls = 0;
  int nr = 0, found = 0;
  /* Prime results and verify the ENTIRE ready set, including bounded epoll
     arrays. No data is consumed; writers remain open. Entire setup is outside
     timing. */
  memset(seen, 0, n);
  for (int attempts = 0; attempts < n + 1; attempts++) {
    if (ep)
      nr = epoll_wait(epfd, events, cap, 0);
    else if (po)
      nr = poll(fds, n, 0);
    else {
      readyset = master;
      struct timeval tv = {0};
      nr = select(maxfd + 1, &readyset, 0, 0, &tv);
    }
    if (nr < 0) {
      fail("prime wait");
    }
    require(nr == (ep ? (r < cap ? r : cap) : r), "prime count");
    int count = 0;
    if (ep) {
      for (int j = 0; j < nr; j++)
        indices[count++] = (int)events[j].data.u64;
    } else
      for (int j = 0; j < n; j++)
        if (po ? (fds[j].revents & POLLIN) : FD_ISSET(pairs[j][0], &readyset))
          indices[count++] = j;
    for (int j = 0; j < count; j++) {
      int index = indices[j];
      require(index >= 0 && index < n && expected[index], "prime set");
      if (!seen[index]) {
        seen[index] = 1;
        found++;
      }
    }
    if (found == r)
      break;
  }
  require(found == r, "prime full set");
  uint64_t ready_hash = 1469598103934665603ULL;
  for (int i = 0; i < n; i++)
    ready_hash = (ready_hash ^ expected[i]) * 1099511628211ULL;
  struct rusage cpu0, cpu1;
  getrusage(RUSAGE_SELF, &cpu0);
  uint64_t begin = now();
  for (uint64_t iteration = 0; iteration < loops; iteration++) {
    if (full) {
      memset(seen, 0, n);
    }
    int distinct = 0;
    do {
      if (!scan_only && !verify_only && !ctl_only) {
        do {
          if (ep)
            nr = epoll_wait(epfd, events, cap, timeout);
          else if (po)
            nr = poll(fds, n, timeout);
          else {
            readyset = master;
            struct timeval tv = {0};
            nr = select(maxfd + 1, &readyset, 0, 0, timeout == 0 ? &tv : NULL);
          }
        } while (nr < 0 && errno == EINTR);
        if (nr < 0) {
          fail("wait");
        }
        require(nr == (ep ? (r < cap ? r : cap) : r), "timed count");
        calls++;
        observed += nr;
      }
      if (!api && !ctl_only) {
        int count = 0;
        if (!verify_only) {
          if (ep) {
            for (int j = 0; j < nr; j++)
              indices[count++] = (int)events[j].data.u64;
          } else
            for (int j = 0; j < n; j++)
              if (po ? (fds[j].revents & POLLIN)
                     : FD_ISSET(pairs[j][0], &readyset))
                indices[count++] = j;
          __asm__ volatile("" : : "r"(indices) : "memory");
          require(count == nr, "scan count");
        } else
          count = nr;
        if (full || verify_only || !strcmp(work, "verify")) {
          if (!full)
            memset(seen, 0, n);
          for (int j = 0; j < count; j++) {
            int index = indices[j];
            require(index >= 0 && index < n && expected[index], "timed set");
            if (!seen[index]) {
              seen[index] = 1;
              distinct++;
            } else
              require(full, "duplicate in batch");
          }
        }
        checksum += count;
      } else
        checksum += nr;
    } while (full && distinct < r);
    for (int j = 0; j < changes; j++) {
      int index = (int)((iteration * (uint64_t)changes + j) % n);
      struct epoll_event ev = {.events = EPOLLIN, .data.u64 = index};
      if (epoll_ctl(epfd, EPOLL_CTL_DEL, pairs[index][0], NULL) ||
          epoll_ctl(epfd, EPOLL_CTL_ADD, pairs[index][0], &ev)) {
        fail("timed ctl");
      }
      controls += 2;
    }
  }
  uint64_t duration = now() - begin;
  getrusage(RUSAGE_SELF, &cpu1);
  printf("{\"ready_hash\":%" PRIu64 ",\"duration_ns\":%" PRIu64
         ",\"setup_epoll_ns\":%" PRIu64 ",\"wait_calls\":%" PRIu64
         ",\"events_observed\":%" PRIu64 ",\"checksum\":%" PRIu64
         ",\"ctl_calls\":%" PRIu64 ",\"user_us\":%" PRIu64
         ",\"system_us\":%" PRIu64
         ",\"min_fd\":%d,\"max_fd\":%d,\"preflight_ready\":%d,\"errors\":0}\n",
         ready_hash, duration, setup, calls, observed, checksum, controls,
         us(cpu1.ru_utime) - us(cpu0.ru_utime),
         us(cpu1.ru_stime) - us(cpu0.ru_stime), pairs[0][0], maxfd, found);
  if (ep) {
    close(epfd);
  }
  for (int i = 0; i < n; i++) {
    close(pairs[i][0]);
    close(pairs[i][1]);
  }
  free(pairs);
  free(order);
  free(indices);
  free(expected);
  free(seen);
  free(fds);
  free(events);
  return 0;
}
