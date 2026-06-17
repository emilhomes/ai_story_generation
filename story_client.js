const axios = require("axios");
const readline = require("readline");
const fs = require("fs");
const path = require("path");

const SERVIDOR_FLASK = "http://192.168.16.76:5000";
const FORGE_API_TXT2IMG = "http://127.0.0.1:7860/sdapi/v1/txt2img";

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// ============================================================
// CONFIGURAÇÃO DE DIRETÓRIOS
// ============================================================
let PASTA_SESSAO = "";

function prepararPastaSessao(seed) {
    const baseDir = path.join(__dirname, "historias_geradas");
    if (!fs.existsSync(baseDir)) fs.mkdirSync(baseDir);

    PASTA_SESSAO = path.join(baseDir, `sessao_${seed}`);
    if (!fs.existsSync(PASTA_SESSAO)) fs.mkdirSync(PASTA_SESSAO);
    console.log(`\n📂 Arquivos serão salvos em: ${PASTA_SESSAO}`);
}

function salvarImagem(base64, nomeArquivo) {
    const filePath = path.join(PASTA_SESSAO, nomeArquivo);
    const buffer = Buffer.from(base64, "base64");
    fs.writeFileSync(filePath, buffer);
    console.log(`      💾 Imagem salva em: ${filePath}`);
}

function registrarLog(conteudo) {
    const filePath = path.join(PASTA_SESSAO, "historia_completa.txt");
    fs.appendFileSync(filePath, conteudo + "\n");
}

function perguntar(texto) {
    return new Promise((resolve) => {
        rl.question(texto, resolve);
    });
}

let SEED_SESSAO = Math.floor(Math.random() * 1000000000);
let IMAGEM_REFERENCIA_GLOBAL = null; 

// ============================================================
// GERAÇÃO DE SEQUÊNCIA COM IP-ADAPTER
// ============================================================
async function gerarSequenciaStoryboard(promptsImagens, microcenasTextos, negativePrompt, numeroCena, dadosDaCena) {
    console.log(`\n🎨 Gerando Storyboard - Cena ${numeroCena} (${microcenasTextos.length} quadros)`);

    const seedCena = SEED_SESSAO; 

    for (let i = 0; i < promptsImagens.length; i++) {
        const promptAtual = promptsImagens[i];
        const acaoTexto = microcenasTextos[i];

        console.log(`   🎬 Quadro ${i + 1}: [${acaoTexto}]`);

        const payloadTxt = {
            prompt: promptAtual,
            negative_prompt: negativePrompt || "",
            steps: 28,                        
            width: 768,
            height: 768,
            sampler_name: "DPM++ 2M Karras",
            cfg_scale: 7.0,                   
            seed: seedCena,
            alwayson_scripts: {},
            override_settings: {
                "CLIP_stop_at_last_layers": 2
            }
        };

        try {
            const response = await axios.post(FORGE_API_TXT2IMG, payloadTxt, { 
                timeout: 180000,
                responseType: 'json'
            });

            if (response.data && response.data.images) {
                const nomeImg = `cena_${numeroCena}_quadro_${i + 1}.png`;
                salvarImagem(response.data.images[0], nomeImg);
                registrarLog(`[IMAGEM: ${nomeImg}] Prompt: ${promptAtual}`);
            }

            console.log(`      ✅ Quadro ${i + 1} concluído.`);
            
            // Se for o primeiro quadro e tivermos dados para publicar, liberamos a apresentação e o NAO!
            if (i === 0 && dadosDaCena) {
                await axios.post(`${SERVIDOR_FLASK}/publicar_cena`, dadosDaCena).catch(() => {});
                dadosDaCena = null; // Para não publicar de novo nos próximos loops
            }
            
        } catch (err) {
            console.log(`      ❌ Erro no Quadro ${i + 1}:`, err.message);
        }
    }
}

// ============================================================
// COMUNICAÇÃO COM O SERVIDOR FLASK
// ============================================================
async function iniciarSessao(nome, tema, skill, genero) {
    try {
        const resp = await axios.post(`${SERVIDOR_FLASK}/iniciar_historia`, { 
            nome, 
            tema, 
            skill,
            genero
        });
        return resp.data;
    } catch (err) {
        console.log("❌ Erro ao conectar ao servidor Flask.");
        return null;
    }
}

async function escolherCena(session_id, node_id, escolha_idx, escolha_texto) {
    try {
        const resp = await axios.post(`${SERVIDOR_FLASK}/escolher`, {
            session_id,
            node_id,
            escolha_idx,
            escolha_texto
        });
        return resp.data;
    } catch (err) {
        console.log("❌ Erro ao escolher cena.");
        return null;
    }
}

function mostrarMenu(titulo, opcoes) {
    console.log(`\n--- ${titulo} ---`);
    opcoes.forEach((op, index) => {
        console.log(`${index + 1}. ${op}`);
    });
}

function mostrarOpcoes(opcoes) {
    mostrarMenu("SUA ESCOLHA", opcoes);
}

// ============================================================
// COMUNICAÇÃO COM O ROBÔ NAO
// ============================================================
async function speakNAO(text) {
    if (!text) return;
    
    // Limpeza básica para o robô não ler caracteres especiais
    const textoLimpo = text
        .replace(/[""«»]/g, '')
        .replace(/[—–]/g, ',')
        .replace(/\.\.\./g, '.')
        .replace(/[*_~`#]/g, '')
        .replace(/\s{2,}/g, ' ')
        .trim();

    try {
        const ROBOT_BRIDGE = SERVIDOR_FLASK.replace(":5000", ":8080");
        await axios.post(`${ROBOT_BRIDGE}/speak`, { text: textoLimpo });
    } catch (e) {
        // Silencioso se o robô não estiver ligado ou erro na bridge
    }
}

const FRASES_ESPERA_INICIO = [
    "Ajustando meus sensores temporais... Só um momento.",
    "Acessando os arquivos históricos... Preparando nossa viagem.",
    "Iniciando os motores de imaginação. Aguarde um instante."
];

const FRASES_ESPERA_MEIO = [
    "Hmm, pensando em como a história continua...",
    "Calculando as consequências da sua escolha... Interessante...",
    "Deixe-me consultar os registros para ver o que acontece agora...",
    "Processando as memórias daquela época... Só um segundo.",
    "Um momento, estou visualizando como essa decisão muda tudo."
];

async function falarEnrolacao(isInicio, escolhaTexto = "") {
    const frasesPensando = isInicio ? FRASES_ESPERA_INICIO : FRASES_ESPERA_MEIO;
    const fraseP = frasesPensando[Math.floor(Math.random() * frasesPensando.length)];
    
    let fraseFinal = fraseP;
    if (!isInicio && escolhaTexto) {
        const confirmacoes = [
            "Hmm, então você selecionou",
            "Boa escolha! Você decidiu ir por",
            "Interessante... você escolheu",
            "Muito bem, vamos seguir por",
            "Legal! Você optou por",
            "Ótimo caminho! Vamos ver o que acontece em"
        ];
        const c = confirmacoes[Math.floor(Math.random() * confirmacoes.length)];
        // Sem aspas para evitar bugs no ALAnimatedSpeech
        fraseFinal = `${c} ${escolhaTexto}. ${fraseP}`;
    }

    console.log(`\n🤖 NAO (Pensando): "${fraseFinal}"`);
    try {
        await axios.post(`${SERVIDOR_FLASK}/definir_pensando`, { frase: fraseFinal });
        // Dá 1.5s para o Flask respirar e o NAO conseguir ler o estado antes de travar a thread na IA
        await new Promise(r => setTimeout(r, 1500));
    } catch (e) {}
}

async function fazerPerguntaModal(pergunta, opcoes) {
    console.log(`\n🗣️ NAO (Pergunta): "${pergunta}"`);
    
    // O backend agora cuida da fala via status="modal".
    await axios.post(`${SERVIDOR_FLASK}/publicar_modal`, { pergunta, opcoes }).catch(()=>{});
    
    let escolhaTexto = "";
    let idxReal = 0;
    
    while(true) {
        try {
            const res = await axios.get(`${SERVIDOR_FLASK}/esperar_escolha`);
            if (res.data && res.data.status === "ok") {
                idxReal = res.data.dados.escolha_idx;
                escolhaTexto = res.data.dados.escolha_texto;
                break;
            }
        } catch (err) {}
        await new Promise(r => setTimeout(r, 1000));
    }
    
    return { idx: idxReal, texto: escolhaTexto };
}

function adicionarOpcoesNaFala(cenaPayload) {
    if (!cenaPayload.tem_opcoes || !cenaPayload.opcoes || cenaPayload.opcoes.length < 2) return;
    const transicoes = [
        "E agora, vamos seguir por",
        "Qual será o nosso próximo passo? Escolha",
        "O que você acha melhor fazer? Podemos ir por",
        "A decisão é sua! Vamos por"
    ];
    const t = transicoes[Math.floor(Math.random() * transicoes.length)];
    // Sem aspas para não bugar o parser do NAO
    cenaPayload.fala_robo += ` ${t} ${cenaPayload.opcoes[0]}, ou por ${cenaPayload.opcoes[1]}?`;
}

// ============================================================
// LOOP PRINCIPAL
// ============================================================
async function main() {
    let contadorCena = 1; // Inicializa o contador

    console.log("\n==================================================");
    console.log("🎬 NAO - EXPLORADORES DA HISTÓRIA");
    console.log("==================================================");

    const nome = await perguntar("Qual o nome da criança? ");
    
    const generos = ["Masculino", "Feminino"];
    mostrarMenu("QUAL O GÊNERO DO PERSONAGEM?", generos);
    const generoIdx = parseInt(await perguntar("Selecione (1-2): ")) - 1;
    const genero = generos[generoIdx] || "Masculino";

    const jornadas = [
        { label: "Alan Turing - Cambridge (1936)", value: "alan_turing", tema: "Cambridge (1936)" },
        { label: "Steve Jobs - Vale do Silício (Apple)", value: "steve_jobs", tema: "Vale do Silício (Apple)" },
        { label: "Katherine Johnson - NASA (NASA Langley)", value: "katherine_johnson", tema: "NASA (NASA Langley)" }
    ];

    mostrarMenu("ESCOLHA SUA JORNADA HISTÓRICA", jornadas.map(j => j.label));
    const jornadaIdx = parseInt(await perguntar("Selecione (1-3): ")) - 1;
    const jornadaEscolhida = jornadas[jornadaIdx] || jornadas[0];

    const tema = jornadaEscolhida.tema;
    const skill = jornadaEscolhida.value;

    console.log("\n⏳ Iniciando montagem do personagem no telão...");

    const pCompCabelo = {
        pergunta: `Oi ${nome}, primeiramente me ajude a imaginar você. Qual o tamanho do seu cabelo?`,
        opcoes: ["Curto", "Médio", "Longo", "Raspado (Careca)"],
        tags: ["short", "medium length", "long", "shaved head"]
    };
    const respCompCabelo = await fazerPerguntaModal(pCompCabelo.pergunta, pCompCabelo.opcoes);

    let tagCabeloFinal = "";
    if (respCompCabelo.idx === 3) {
        tagCabeloFinal = "shaved head";
    } else {
        const pTipoCabelo = {
            pergunta: "Legal! E como é o tipo do seu cabelo?",
            opcoes: ["Liso", "Ondulado", "Cacheado", "Crespo"],
            tags: ["straight", "wavy", "curly", "coily"]
        };
        const respTipoCabelo = await fazerPerguntaModal(pTipoCabelo.pergunta, pTipoCabelo.opcoes);

        const pCorCabelo = {
            pergunta: "Entendi! E qual é a cor do seu cabelo?",
            opcoes: ["Preto", "Castanho", "Loiro", "Ruivo"],
            tags: ["black hair", "brown hair", "blonde hair", "red hair"]
        };
        const respCorCabelo = await fazerPerguntaModal(pCorCabelo.pergunta, pCorCabelo.opcoes);
        
        tagCabeloFinal = `${pCompCabelo.tags[respCompCabelo.idx]} ${pTipoCabelo.tags[respTipoCabelo.idx]} ${pCorCabelo.tags[respCorCabelo.idx]}`;
    }

    const pPele = {
        pergunta: "Perfeito! E qual é a cor da sua pele?",
        opcoes: ["Pele Clara", "Pele Morena", "Pele Negra", "Pele Amarelada"],
        tags: ["light skin", "tanned skin", "dark skin", "pale skin"]
    };
    const respPele = await fazerPerguntaModal(pPele.pergunta, pPele.opcoes);

    const pOlhos = {
        pergunta: "Quase lá. E os seus olhos?",
        opcoes: ["Olhos Castanhos", "Olhos Verdes", "Olhos Azuis", "Olhos Escuros"],
        tags: ["brown eyes", "green eyes", "blue eyes", "dark eyes"]
    };
    const respOlhos = await fazerPerguntaModal(pOlhos.pergunta, pOlhos.opcoes);

    // Roupa automática baseada na jornada
    let roupaTag = "period-appropriate clothing";
    if (skill === "alan_turing") {
        roupaTag = "casual 1930s clothes, vintage sweater and trousers";
    } else if (skill === "steve_jobs") {
        roupaTag = "casual 1970s clothes, vintage turtleneck and jeans";
    } else if (skill === "katherine_johnson") {
        roupaTag = genero === "Feminino" ? "formal 1960s suit, elegant vintage dress" : "formal 1960s suit, elegant vintage suit";
    }

    // Constrói a string do prompt de personagem
    const generoIngles = genero === "Feminino" ? "1girl" : "1boy";
    const studentVisualFixo = `${generoIngles}, ${tagCabeloFinal}, ${pPele.tags[respPele.idx]}, ${pOlhos.tags[respOlhos.idx]}, ${roupaTag}`;

    console.log(`\n✅ Visual montado: ${studentVisualFixo}`);

    console.log("\n⏳ Preparando o mundo e abrindo o livro...");
    falarEnrolacao(true); // O robô enrola enquanto a IA gera a primeira cena
    const dados = await axios.post(`${SERVIDOR_FLASK}/iniciar_historia`, { 
        nome, tema, skill, genero, visual_fixo: studentVisualFixo
    }).then(r => r.data).catch(() => null);

    if (!dados || dados.status !== "sucesso") {
        console.log("Erro ao iniciar.");
        process.exit(0);
    }

    // AGORA SIM: Criamos a pasta com o ID que o servidor nos deu
    SEED_SESSAO = dados.session_id; 
    prepararPastaSessao(SEED_SESSAO);
    registrarLog(`ALUNO: ${nome}\nTEMA: ${tema}\nSKILL: ${skill}\nSESSION_ID: ${SEED_SESSAO}\nVISUAL: ${studentVisualFixo}\n`);

    let session_id = dados.session_id;
    let node_id = dados.node_id;
    let temOpcoes = dados.tem_opcoes;
    const negative = dados.negative_prompt || "";

    console.log(`\n📖 CENA ${contadorCena}:`);
    console.log(dados.historia_original);
    registrarLog(`\n--- CENA ${contadorCena} ---\n${dados.historia_original}\n`);

    // Primeira cena: gerar o primeiro quadro SEM IP-Adapter (referência)
    if (dados.prompts_imagens && dados.prompts_imagens.length > 0) {
        console.log("\n📸 Gerando imagem de referência...");
        await gerarPrimeiroQuadro(dados.prompts_imagens[0], dados.microcenas_textos[0], negative);

        // PUBLICAR CENA APÓS A PRIMEIRA IMAGEM ESTAR PRONTA
        await axios.post(`${SERVIDOR_FLASK}/publicar_cena`, dados).catch(() => {});

        if (dados.prompts_imagens.length > 1) {
            const promptsRestantes = dados.prompts_imagens.slice(1);
            const microcenasRestantes = dados.microcenas_textos.slice(1);
            await gerarSequenciaStoryboard(promptsRestantes, microcenasRestantes, negative, contadorCena, null); // null pq já foi publicada
        }
    } else {
        await axios.post(`${SERVIDOR_FLASK}/publicar_cena`, dados).catch(() => {});
    }

    // opcoes_atuais guarda SEMPRE as opções da cena mais recente
    let opcoes_atuais = dados.opcoes || [];

    while (temOpcoes) {
        console.log("\n👀 Aguardando o jogador escolher uma opção no telão...");
        let escolhaTexto = "";
        let idxReal = 0;

        while (true) {
            try {
                const res = await axios.get(`${SERVIDOR_FLASK}/esperar_escolha`);
                if (res.data && res.data.status === "ok") {
                    idxReal = res.data.dados.escolha_idx;
                    escolhaTexto = res.data.dados.escolha_texto;
                    break;
                }
            } catch (err) {}
            // Espera 1 segundo antes de checar novamente
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        contadorCena++;
        console.log(`\n⏳ O jogador escolheu: "${escolhaTexto}"`);
        registrarLog(`\nESCOLHA DO USUÁRIO: ${escolhaTexto}`);

        falarEnrolacao(false, escolhaTexto); // O robô confirma a escolha e enrola

        const resposta = await escolherCena(session_id, node_id, idxReal, escolhaTexto);
        if (!resposta || resposta.status !== "sucesso") {
            console.log("❌ Erro na escolha.");
            break;
        }

        node_id = resposta.node_id;
        temOpcoes = resposta.tem_opcoes;

        console.log(`\n📖 CENA ${contadorCena}:`);
        console.log(resposta.historia_original);
        registrarLog(`\n--- CENA ${contadorCena} ---\n${resposta.historia_original}\n`);

        if (resposta.prompts_imagens && resposta.prompts_imagens.length > 0) {
            await gerarSequenciaStoryboard(resposta.prompts_imagens, resposta.microcenas_textos, negative, contadorCena, resposta);
        } else {
            await axios.post(`${SERVIDOR_FLASK}/publicar_cena`, resposta).catch(() => {});
        }

        // CORREÇÃO: atualiza opcoes_atuais IMEDIATAMENTE para a próxima iteração
        opcoes_atuais = resposta.opcoes || [];

        if (!temOpcoes) console.log("\n🎬 Fim da história!");
    }

    console.log(`\n✨ Sessão encerrada! Todos os arquivos estão em: ${PASTA_SESSAO}`);
    rl.close();
}

// ============================================================
// GERAÇÃO DO PRIMEIRO QUADRO (referência inicial)
// ============================================================
async function gerarPrimeiroQuadro(promptImagem, microcenaTexto, negativePrompt) {
    console.log(`   🎬 Quadro REFERÊNCIA: [${microcenaTexto}]`);

    const payloadTxt = {
        prompt: promptImagem,
        negative_prompt: negativePrompt || "",
        steps: 25,
        width: 768,
        height: 768,
        sampler_name: "DPM++ 2M Karras",
        cfg_scale: 7.0,
        seed: SEED_SESSAO + 1,
        save_images: true,
        send_images: true,
        override_settings: {
            "CLIP_stop_at_last_layers": 2
        }
    };

    try {
        const response = await axios.post(FORGE_API_TXT2IMG, payloadTxt, { 
            timeout: 120000,
            responseType: 'json'
        });

        if (response.data && response.data.images && response.data.images.length > 0) {
            IMAGEM_REFERENCIA_GLOBAL = response.data.images[0];

            // Salva fisicamente
            salvarImagem(IMAGEM_REFERENCIA_GLOBAL, "cena_1_referencia_global.png");
            registrarLog(`[IMAGEM: cena_1_referencia_global.png] Prompt: ${promptImagem}`);

            console.log(`      ✅ Quadro de referência gerado e salvo!`);
        }
    } catch (err) {
        console.log(`      ❌ Erro ao gerar quadro de referência.`, err.message);
    }
}

main();