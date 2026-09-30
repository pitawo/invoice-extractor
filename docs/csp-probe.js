// 「わざと外部への通信を試す」ボタン専用。データは何も載せず、空の GET を1回試みるだけ。
// CSP（connect-src 'none'）が効いていれば、ブラウザが送信前に止める。
(function () {
  "use strict";
  var btn = document.getElementById("try-net");
  var out = document.getElementById("try-net-result");
  var blocked = null;
  document.addEventListener("securitypolicyviolation", function (e) {
    blocked = e.violatedDirective + " が " + e.blockedURI + " を止めました";
  });
  btn.addEventListener("click", function () {
    blocked = null;
    out.textContent = "試しています…";
    fetch("https://example.com/", { method: "GET", credentials: "omit", cache: "no-store" }).then(function () {
      out.textContent = "通信できてしまいました（この設定は効いていません）";
    }, function () {
      // イベントは非同期で届くことがあるので、少し待ってから表示する
      setTimeout(function () {
        out.textContent = blocked
          ? "ブロックされました：" + blocked
          : "通信に失敗しましたが、CSP による遮断は確認できませんでした（ネットワークの問題かもしれません）";
      }, 50);
    });
  });
})();
