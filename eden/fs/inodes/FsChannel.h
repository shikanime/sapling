/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This software may be used and distributed according to the terms of the
 * GNU General Public License version 2.
 */

#pragma once

#include "eden/fs/utils/FsChannelTypes.h"
#include "eden/fs/utils/ImmediateFuture.h"

namespace facebook::eden {

class FsStopData {
 public:
  virtual ~FsStopData() = default;

  /**
   * If true, the mount has been stopped and should be considered unmounted.
   *
   * If false, this mount is intended to be taken over by a new EdenFS daemon.
   */
  virtual bool isUnmounted() = 0;

  virtual FsChannelInfo extractTakeoverInfo() = 0;
};

using FsStopDataPtr = std::unique_ptr<FsStopData>;

/**
 * A connection to a userspace filesystem driver.
 *
 * In practice, this is FuseChannel, Nfsd3, or PrjfsChannel.
 */
class FsChannel {
 public:
  virtual ~FsChannel() = default;

  /**
   * Returns a short, human-readable (or at least loggable) name for this
   * FsChannel type.
   *
   * e.g. "fuse", "nfs3", "prjfs"
   */
  virtual const char* getName() const = 0;

  /**
   * Ask this FsChannel to stop for a takeover request.
   *
   * Returns true if takeover is supported and a takeover attempt has begun.
   */
  virtual bool takeoverStop() = 0;

  /**
   * Neither FuseChannel and Nfsd3 can be deleted from arbitrary threads.
   *
   * destroy() initiates the destruction process, but the delete will occur on
   * another thread.
   *
   * The FsChannel may not be accessed after destroy() is called.
   */
  virtual void destroy() = 0;

  /**
   * During checkout or other Thrift calls that modify the filesystem, those
   * modifications may be invisible to the filesystem's own caches. Therefore,
   * we send fine-grained invalidation messages to the FsChannel. Those
   * invalidations may be asynchronous, but we need to ensure that they have
   * been observed by the time the Thrift call completes.
   *
   * You may think of completeInvalidations() as a fence; after
   * completeInvalidations() completes, invalidations of inode attributes, inode
   * content, and name lookups are guaranteed to be observable.
   */
  FOLLY_NODISCARD virtual ImmediateFuture<folly::Unit>
  completeInvalidations() = 0;
};

/**
 * FsChannelDeleter acts as a deleter argument for std::shared_ptr or
 * std::unique_ptr.
 */
class FsChannelDeleter {
 public:
  void operator()(FsChannel* channel) {
    channel->destroy();
  }
};

} // namespace facebook::eden
