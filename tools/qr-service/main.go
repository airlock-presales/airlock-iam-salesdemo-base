// qr-service - returns a QR code (PNG) for the text in query parameter "txt"
//
//	GET /qrcode?txt=<text>[&size=<pixels>]   PNG image, size 64..1024 (default 300)
//	GET /healthz                             liveness/readiness
//
// Used by the IAM self-registration with identity proofing (PXL Vision): the browser loads
// the QR code of the PXL workflow link through Airlock Microgateway (/qr/).
package main

import (
	"log"
	"net/http"
	"os"
	"strconv"

	qrcode "github.com/skip2/go-qrcode"
)

const maxTextLength = 2048

func qrHandler(w http.ResponseWriter, r *http.Request) {
	txt := r.URL.Query().Get("txt")
	if txt == "" || len(txt) > maxTextLength {
		http.Error(w, "parameter txt missing or too long", http.StatusBadRequest)
		return
	}
	size := 300
	if s := r.URL.Query().Get("size"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil || v < 64 || v > 1024 {
			http.Error(w, "parameter size must be 64..1024", http.StatusBadRequest)
			return
		}
		size = v
	}
	png, err := qrcode.Encode(txt, qrcode.Medium, size)
	if err != nil {
		http.Error(w, "failed to create QR code", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "image/png")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(png)
}

func main() {
	addr := ":8080"
	if p := os.Getenv("PORT"); p != "" {
		addr = ":" + p
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /qrcode", qrHandler)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
	log.Printf("qr-service listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
