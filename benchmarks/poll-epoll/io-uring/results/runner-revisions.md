# 測定後のrunner差分

実測時run.pyはresults/main/source-snapshot/io-uring/run.pyに保存した。公開runnerでは標準ライブラリ場所を固定ZVM pathからzig envのstd_dirへ変更し、追加fault-testsをゲートへ追加した。性能ループ・条件・seed・順序・測定binaryのソースは変更していない。正確な当時の系列はsnapshotとenvironment.jsonのSHAを参照する。
