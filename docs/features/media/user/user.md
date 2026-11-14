# Media tools

Enable **Media Tools** under **Settings → Features**. For playback, see [Video Player](video-player.md).

## Rename MKA chapters from a CSV

## Prepare the folder

Keep one headerless CSV beside files such as `Chapter_01.mka`. Row 1 is chapter 1. Give each matching row a chapter number and title.

```text
1,Introduction
2,The journey
```

## Rename

Choose **Debug → Rename MKA from CSV…**, select the folder, choose **Review names**, then **Apply reviewed names**. Fix missing titles, invalid filename characters or collisions before retrying.

Keep a copy if you need the original names. There is no Undo after success. If rollback fails after cancellation or error, keep staged files and recover them using the reported paths.

## More help

- [Using Logistics](../../../user/user.md)
- [Media Tools on mobile](../user_mobile/user_mobile.md)
- [Bulk Rename](../../bulk_rename/user/user.md)
