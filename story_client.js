const axios = require("axios");
const readline = require("readline");
const fs = require("fs");
const path = require("path");

const SERVIDOR_FLASK = "http://localhost:5000";

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

function salvarImagem(buffer, nomeArquivo) {
    const filePath = path.join(PASTA_SESSAO, nomeArquivo);
    fs.writeFileSync(filePath, buffer);
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
// GERAÇÃO DE SEQUÊNCIA COM POLLINATIONS.AI (PARALELO + RETRY)
// ============================================================
async function gerarComRetry(url, maxRetries = 2) {
    let lastError = null;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response = await axios.get(url, { 
                timeout: 180000,
                responseType: 'arraybuffer'
            });
            return response.data;
        } catch (err) {
            lastError = err;
            if (attempt < maxRetries) {
                console.log(`      ⚠️ Tentativa ${attempt + 1} falhou. Retentando em 3s...`);
                await new Promise(res => setTimeout(res, 3000));
            }
        }
    }
    throw lastError;
}

async function gerarSequenciaStoryboard(promptsImagens, microcenasTextos, negativePrompt, numeroCena) {
    console.log(`\n🎨 Gerando Storyboard em paralelo - Cena ${numeroCena} (${microcenasTextos.length} quadros)`);

    const seedCena = SEED_SESSAO; 

    const promessas = promptsImagens.map(async (promptAtual, i) => {
        const acaoTexto = microcenasTextos[i];
        const quadroNum = i + 1;
        const url = `https://image.pollinations.ai/prompt/${encodeURIComponent(promptAtual)}?width=768&height=768&seed=${seedCena}&nologo=true`;

        try {
            const buffer = await gerarComRetry(url);
            if (buffer) {
                const nomeImg = `cena_${numeroCena}_quadro_${quadroNum}.png`;
                salvarImagem(buffer, nomeImg);
                registrarLog(`[IMAGEM: ${nomeImg}] Prompt: ${promptAtual}`);
                console.log(`      ✅ Quadro ${quadroNum} concluído: [${acaoTexto}]`);
            }
        } catch (err) {
            console.log(`      ❌ Erro no Quadro ${quadroNum} após tentativas:`, err.message);
        }
    });

    await Promise.all(promessas);
}

// ============================================================
// COMUNICAÇÃO COM O SERVIDOR FLASK
// ============================================================
async function iniciarSessao(nome, tema, skill) {
    try {
        const resp = await axios.post(`${SERVIDOR_FLASK}/iniciar_historia`, { 
            nome, 
            tema, 
            skill 
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
// LOOP PRINCIPAL
// ============================================================
async function main() {
    SEED_SESSAO = Math.floor(Math.random() * 1000000000);
    prepararPastaSessao(SEED_SESSAO);

    IMAGEM_REFERENCIA_GLOBAL = null;
    let contadorCena = 1;

    console.log("\n==================================================");
    console.log("🎬 NAO - AVENTURAS SOCIOEMOCIONAIS");
    console.log("==================================================");

    const nome = await perguntar("Qual o nome da criança? ");
    
    const temas = ["Escola", "Floresta Encantada", "Fundo do Mar", "Fazenda e Animais", "Espaço", "Parque de Diversões", "Fantasia"];
    mostrarMenu("ESCOLHA O MUNDO", temas);
    const temaIdx = parseInt(await perguntar(`Selecione (1-${temas.length}): `)) - 1;
    const tema = temas[temaIdx] || "Escola";

    const skills = [
        { label: "Fazer amigos", value: "socializacao" },
        { label: "Entender sentimentos", value: "sentimentos" },
        { label: "Ser corajoso", value: "coragem" }
    ];
    mostrarMenu("O QUE VAMOS PRATICAR HOJE?", skills.map(s => s.label));
    const skillIdx = parseInt(await perguntar("Selecione (1-3): ")) - 1;
    const skill = (skills[skillIdx] || skills[0]).value;

    registrarLog(`ALUNO: ${nome}\nTEMA: ${tema}\nSKILL: ${skill}\nSEED: ${SEED_SESSAO}\n`);

    console.log("\n⏳ Preparando o mundo e abrindo o livro...");
    const dados = await iniciarSessao(nome, tema, skill);

    if (!dados || dados.status !== "sucesso") {
        console.log("Erro ao iniciar.");
        process.exit(0);
    }

    let session_id = dados.session_id;
    let node_id = dados.node_id;
    let temOpcoes = dados.tem_opcoes;
    const negative = dados.negative_prompt || "";

    console.log(`\n📖 CENA ${contadorCena}:`);
    console.log(dados.historia_original);
    registrarLog(`\n--- CENA ${contadorCena} ---\n${dados.historia_original}\n`);

    // Primeira cena: gerar o primeiro quadro (referência)
    if (dados.prompts_imagens && dados.prompts_imagens.length > 0) {
        console.log("\n📸 Gerando imagem de referência...");
        await gerarPrimeiroQuadro(dados.prompts_imagens[0], dados.microcenas_textos[0], negative);

        if (dados.prompts_imagens.length > 1) {
            const promptsRestantes = dados.prompts_imagens.slice(1);
            const microcenasRestantes = dados.microcenas_textos.slice(1);
            await gerarSequenciaStoryboard(promptsRestantes, microcenasRestantes, negative, contadorCena);
        }
    }

    if (temOpcoes) mostrarOpcoes(dados.opcoes);

    while (temOpcoes) {
        const escolhaStr = await perguntar("\n👉 Escolha (1-2) ou sair: ");
        if (escolhaStr.toLowerCase() === "sair") break;

        const idx = parseInt(escolhaStr);
        if (isNaN(idx) || idx < 1 || idx > 2) {
            console.log("❌ Opção inválida.");
            continue;
        }

        contadorCena++;
        const escolhaTexto = dados.opcoes[idx - 1];
        console.log(`\n⏳ Você escolheu: "${escolhaTexto}"`);
        registrarLog(`\nESCOLHA DO USUÁRIO: ${escolhaTexto}`);

        const resposta = await escolherCena(session_id, node_id, idx - 1, escolhaTexto);
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
            await gerarSequenciaStoryboard(resposta.prompts_imagens, resposta.microcenas_textos, negative, contadorCena);
        }

        if (temOpcoes) mostrarOpcoes(resposta.opcoes);
        else console.log("\n🎬 Fim da história!");

        dados.opcoes = resposta.opcoes;
    }

    console.log(`\n✨ Sessão encerrada! Todos os arquivos estão em: ${PASTA_SESSAO}`);
    rl.close();
}

// ============================================================
// GERAÇÃO DO PRIMEIRO QUADRO (referência inicial)
// ============================================================
async function gerarPrimeiroQuadro(promptImagem, microcenaTexto, negativePrompt) {
    console.log(`   🎬 Quadro REFERÊNCIA: [${microcenaTexto}]`);

    // URL da Pollinations.ai (usando seed + 1 para diferenciar levemente se necessário, ou manter consistente)
    const url = `https://image.pollinations.ai/prompt/${encodeURIComponent(promptImagem)}?width=768&height=768&seed=${SEED_SESSAO + 1}&nologo=true`;

    try {
        const buffer = await gerarComRetry(url);

        if (buffer) {
            // Salva fisicamente
            salvarImagem(buffer, "cena_1_referencia_global.png");
            registrarLog(`[IMAGEM: cena_1_referencia_global.png] Prompt: ${promptImagem}`);

            console.log(`      ✅ Quadro de referência gerado e salvo!`);
        }
    } catch (err) {
        console.log(`      ❌ Erro ao gerar quadro de referência após tentativas:`, err.message);
    }
}

main();