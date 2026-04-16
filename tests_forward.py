import unittest

import forward_weibo_to_bili as fw


class NormalizeUidTests(unittest.TestCase):
    def test_normalize_one_uid_from_m_weibo_url(self):
        self.assertEqual(
            fw.normalize_one_uid("https://m.weibo.cn/u/5657426591?t=0"),
            "5657426591",
        )

    def test_normalize_uids_merge_and_dedup(self):
        self.assertEqual(
            fw.normalize_uids(
                "https://m.weibo.cn/u/5657426591",
                "5657426591,1234567890,https://m.weibo.cn/u/1234567890",
            ),
            ["5657426591", "1234567890"],
        )


class BuildTextTests(unittest.TestCase):
    def test_build_forward_text(self):
        mblog = {
            "user": {"screen_name": "测试用户"},
            "text": "第一行<br/>第二行",
        }
        content = fw.build_forward_text(mblog, "转自{name}微博：\n\n")
        self.assertIn("转自测试用户微博：", content)
        self.assertIn("第一行\n第二行", content)


if __name__ == "__main__":
    unittest.main()
